"""Online per-turn / per-session / run-level token & offload accounting.

Token counts come only from API ``usage`` fields (no char estimates).
Persisted after every turn under ``stats_dir``.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def require_usage_tokens(usage: dict[str, Any] | None, *, where: str) -> tuple[int, int]:
    """Require API usage; never estimate. Raises if missing/incomplete."""
    if not usage:
        raise RuntimeError(f"{where}: response missing usage; refuse to estimate tokens")
    inp = usage.get("prompt_tokens")
    if inp is None:
        inp = usage.get("input_tokens")
    out = usage.get("completion_tokens")
    if out is None:
        out = usage.get("output_tokens")
    if inp is None or out is None:
        raise RuntimeError(f"{where}: usage incomplete (need prompt+completion tokens): {usage!r}")
    return int(inp), int(out)


@dataclass
class TurnStats:
    turn: int
    offloaded: bool = False
    offload_outside_think: bool = False
    slm_prompt_tokens: int = 0
    slm_completion_tokens: int = 0
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0
    elapsed_sec: float = 0.0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "turn": self.turn,
            "offloaded": self.offloaded,
            "offload_outside_think": self.offload_outside_think,
            "slm_prompt_tokens": self.slm_prompt_tokens,
            "slm_completion_tokens": self.slm_completion_tokens,
            "llm_prompt_tokens": self.llm_prompt_tokens,
            "llm_completion_tokens": self.llm_completion_tokens,
            "elapsed_sec": self.elapsed_sec,
        }
        if self.error:
            d["error"] = self.error
        return d


@dataclass
class SessionStats:
    sid: str
    instance_hint: str = ""
    turns: int = 0
    offload_count: int = 0
    offload_outside_think_count: int = 0
    slm_prompt_tokens: int = 0
    slm_completion_tokens: int = 0
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0
    last_offload_n: int | None = None
    per_turn: list[TurnStats] = field(default_factory=list)
    updated_at: float = field(default_factory=time.time)

    def record_turn(self, turn: TurnStats) -> None:
        self.turns += 1
        self.slm_prompt_tokens += int(turn.slm_prompt_tokens)
        self.slm_completion_tokens += int(turn.slm_completion_tokens)
        self.llm_prompt_tokens += int(turn.llm_prompt_tokens)
        self.llm_completion_tokens += int(turn.llm_completion_tokens)
        if turn.offloaded:
            self.offload_count += 1
        if turn.offload_outside_think:
            self.offload_outside_think_count += 1
        self.per_turn.append(turn)
        self.updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "sid": self.sid,
            "instance_hint": self.instance_hint,
            "turns": self.turns,
            "offload_count": self.offload_count,
            "offload_outside_think_count": self.offload_outside_think_count,
            "slm_prompt_tokens": self.slm_prompt_tokens,
            "slm_completion_tokens": self.slm_completion_tokens,
            "llm_prompt_tokens": self.llm_prompt_tokens,
            "llm_completion_tokens": self.llm_completion_tokens,
            "last_offload_n": self.last_offload_n,
            "updated_at": self.updated_at,
            "per_turn": [t.to_dict() for t in self.per_turn],
        }


class StatsStore:
    """Thread-safe in-memory store with durable JSON snapshots under stats_dir."""

    def __init__(self, stats_dir: str | Path | None = None) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, SessionStats] = {}
        self.stats_dir = Path(stats_dir) if stats_dir else None
        if self.stats_dir is not None:
            self.stats_dir.mkdir(parents=True, exist_ok=True)
            (self.stats_dir / "sessions").mkdir(parents=True, exist_ok=True)

    def get_or_create(self, sid: str, *, instance_hint: str = "") -> SessionStats:
        with self._lock:
            s = self._sessions.get(sid)
            if s is None:
                s = SessionStats(sid=sid, instance_hint=instance_hint or "")
                self._sessions[sid] = s
            elif instance_hint and not s.instance_hint:
                s.instance_hint = instance_hint
            return s

    def record_and_persist(self, sid: str, turn: TurnStats, *, instance_hint: str = "", last_offload_n: int | None = None) -> SessionStats:
        with self._lock:
            s = self._sessions.get(sid)
            if s is None:
                s = SessionStats(sid=sid, instance_hint=instance_hint or "")
                self._sessions[sid] = s
            elif instance_hint and not s.instance_hint:
                s.instance_hint = instance_hint
            s.record_turn(turn)
            if last_offload_n is not None:
                s.last_offload_n = last_offload_n
            snap = s.to_dict()
            summary = self._summary_unlocked()
        self._write_session(sid, snap)
        self._write_summary(summary)
        return s

    def summary(self) -> dict[str, Any]:
        with self._lock:
            return self._summary_unlocked()

    def _summary_unlocked(self) -> dict[str, Any]:
        sessions = [s.to_dict() for s in self._sessions.values()]
        totals = {
            "sessions": len(sessions),
            "turns": 0,
            "offload_count": 0,
            "offload_outside_think_count": 0,
            "slm_prompt_tokens": 0,
            "slm_completion_tokens": 0,
            "llm_prompt_tokens": 0,
            "llm_completion_tokens": 0,
        }
        for s in sessions:
            for k in (
                "turns",
                "offload_count",
                "offload_outside_think_count",
                "slm_prompt_tokens",
                "slm_completion_tokens",
                "llm_prompt_tokens",
                "llm_completion_tokens",
            ):
                totals[k] += int(s.get(k) or 0)
        return {
            "updated_at": time.time(),
            "totals": totals,
            "sessions": sessions,
        }

    def _write_session(self, sid: str, snap: dict[str, Any]) -> None:
        if self.stats_dir is None:
            return
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in sid)[:120]
        path = self.stats_dir / "sessions" / f"{safe}.json"
        try:
            path.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            logger.exception("failed to write session stats %s", path)

    def _write_summary(self, summary: dict[str, Any]) -> None:
        if self.stats_dir is None:
            return
        path = self.stats_dir / "summary.json"
        try:
            path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            logger.exception("failed to write summary stats %s", path)
