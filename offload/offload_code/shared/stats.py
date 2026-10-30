"""Online per-turn / per-session / run-level token & offload accounting.

Token counts come only from API ``usage`` fields (no char estimates).
Persisted after every turn under ``stats_dir``.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _json_usage(usage: dict[str, Any] | None) -> dict[str, Any] | None:
    """Keep the API usage object as returned. Drop it if it is not JSON."""
    if not isinstance(usage, dict):
        return None
    try:
        return json.loads(json.dumps(usage))
    except (TypeError, ValueError):
        return None


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
    slm_usage: dict[str, Any] | None = None
    llm_usage: dict[str, Any] | None = None
    mean_think_entropy: float | None = None
    think_tokens: int = 0
    entropy_threshold: float | None = None
    entropy_unavailable: bool = False

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
            "mean_think_entropy": (
                None if self.mean_think_entropy is None else round(float(self.mean_think_entropy), 6)
            ),
            "think_tokens": self.think_tokens,
            "entropy_threshold": self.entropy_threshold,
            "entropy_unavailable": self.entropy_unavailable,
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
    task: str = ""
    think_entropy_sum: float = 0.0
    think_entropy_count: int = 0
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
        if turn.mean_think_entropy is not None:
            self.think_entropy_sum += float(turn.mean_think_entropy)
            self.think_entropy_count += 1
        self.per_turn.append(turn)
        self.updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        mean = None
        if self.think_entropy_count:
            mean = round(self.think_entropy_sum / self.think_entropy_count, 6)
        return {
            "sid": self.sid,
            "task": self.task or self.instance_hint or self.sid,
            "instance_hint": self.instance_hint,
            "turns": self.turns,
            "offload_count": self.offload_count,
            "offload_outside_think_count": self.offload_outside_think_count,
            "slm_prompt_tokens": self.slm_prompt_tokens,
            "slm_completion_tokens": self.slm_completion_tokens,
            "llm_prompt_tokens": self.llm_prompt_tokens,
            "llm_completion_tokens": self.llm_completion_tokens,
            "last_offload_n": self.last_offload_n,
            "mean_think_entropy": mean,
            "think_entropy_count": self.think_entropy_count,
            "updated_at": self.updated_at,
            "per_turn": [t.to_dict() for t in self.per_turn],
        }


class StatsStore:
    """Thread-safe in-memory store with durable JSON snapshots under stats_dir.

    Canonical on-disk layout (under ``stats_dir/token_usage/``)::

        turns.jsonl
        turn_trace.jsonl
        summary_task.json
        summary_session.json
    """

    def __init__(self, stats_dir: str | Path | None = None) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, SessionStats] = {}
        self.stats_dir = Path(stats_dir) if stats_dir else None
        self.token_usage_dirs: list[Path] = []
        if self.stats_dir is not None:
            self.stats_dir.mkdir(parents=True, exist_ok=True)
            (self.stats_dir / "sessions").mkdir(parents=True, exist_ok=True)
            self.token_usage_dirs.append(self.stats_dir / "token_usage")
        extra = os.environ.get("TOKEN_USAGE_DIR", "").strip()
        if extra:
            p = Path(extra)
            if self.stats_dir is not None and p.resolve() == self.stats_dir.resolve():
                p = self.stats_dir / "token_usage"
            if all(p.resolve() != existing.resolve() for existing in self.token_usage_dirs):
                self.token_usage_dirs.append(p)
        for path in self.token_usage_dirs:
            path.mkdir(parents=True, exist_ok=True)

    def get_or_create(self, sid: str, *, instance_hint: str = "") -> SessionStats:
        with self._lock:
            s = self._sessions.get(sid)
            if s is None:
                s = SessionStats(sid=sid, instance_hint=instance_hint or "")
                self._sessions[sid] = s
            elif instance_hint and not s.instance_hint:
                s.instance_hint = instance_hint
            return s

    def record_and_persist(
        self,
        sid: str,
        turn: TurnStats,
        *,
        instance_hint: str = "",
        task: str = "",
        last_offload_n: int | None = None,
    ) -> SessionStats:
        with self._lock:
            s = self._sessions.get(sid)
            if s is None:
                s = SessionStats(sid=sid, instance_hint=instance_hint or "", task=task or instance_hint or "")
                self._sessions[sid] = s
            else:
                if instance_hint and not s.instance_hint:
                    s.instance_hint = instance_hint
                if task and not s.task:
                    s.task = task
            s.record_turn(turn)
            if last_offload_n is not None:
                s.last_offload_n = last_offload_n
            snap = s.to_dict()
            summary = self._summary_unlocked()
            token_summary = self._token_summary_unlocked()
            row = {
                "time": round(time.time(), 3),
                "sid": sid,
                "task": s.task or s.instance_hint or sid,
                "turn": turn.turn,
                "offloaded": bool(turn.offloaded),
                "slm_prompt_tokens": int(turn.slm_prompt_tokens),
                "slm_completion_tokens": int(turn.slm_completion_tokens),
                "llm_prompt_tokens": int(turn.llm_prompt_tokens),
                "llm_completion_tokens": int(turn.llm_completion_tokens),
                "slm_usage": _json_usage(turn.slm_usage),
                "llm_usage": _json_usage(turn.llm_usage),
            }
            self._append_token_turn(row)
            self._write_summary_task(token_summary)
            self._write_summary_session(summary)
        self._write_session(sid, snap)
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
            "think_entropy_count": 0,
        }
        entropy_sum = 0.0
        for s in self._sessions.values():
            totals["turns"] += int(s.turns)
            totals["offload_count"] += int(s.offload_count)
            totals["offload_outside_think_count"] += int(s.offload_outside_think_count)
            totals["slm_prompt_tokens"] += int(s.slm_prompt_tokens)
            totals["slm_completion_tokens"] += int(s.slm_completion_tokens)
            totals["llm_prompt_tokens"] += int(s.llm_prompt_tokens)
            totals["llm_completion_tokens"] += int(s.llm_completion_tokens)
            totals["think_entropy_count"] += int(s.think_entropy_count)
            entropy_sum += float(s.think_entropy_sum)
        totals["mean_think_entropy"] = (
            round(entropy_sum / totals["think_entropy_count"], 6) if totals["think_entropy_count"] else None
        )
        return {
            "updated_at": time.time(),
            "totals": totals,
            "sessions": sessions,
        }

    def _token_summary_unlocked(self) -> dict[str, Any]:
        tasks = []
        totals = {
            "tasks": 0,
            "turns": 0,
            "offload_turns": 0,
            "slm_prompt_tokens": 0,
            "slm_completion_tokens": 0,
            "llm_prompt_tokens": 0,
            "llm_completion_tokens": 0,
        }
        for s in self._sessions.values():
            row = {
                "task": s.task or s.instance_hint or s.sid,
                "sid": s.sid,
                "turns": s.turns,
                "offload_turns": s.offload_count,
                "slm_prompt_tokens": s.slm_prompt_tokens,
                "slm_completion_tokens": s.slm_completion_tokens,
                "llm_prompt_tokens": s.llm_prompt_tokens,
                "llm_completion_tokens": s.llm_completion_tokens,
            }
            tasks.append(row)
            totals["tasks"] += 1
            totals["turns"] += s.turns
            totals["offload_turns"] += s.offload_count
            totals["slm_prompt_tokens"] += s.slm_prompt_tokens
            totals["slm_completion_tokens"] += s.slm_completion_tokens
            totals["llm_prompt_tokens"] += s.llm_prompt_tokens
            totals["llm_completion_tokens"] += s.llm_completion_tokens
        tasks.sort(key=lambda item: item["task"])
        return {"updated_at": time.time(), "totals": totals, "tasks": tasks}

    def append_turn_trace(self, row: dict[str, Any]) -> None:
        """One finished turn: entropy, SLM original text, and LLM text when it ran."""
        line = json.dumps(row, ensure_ascii=False) + "\n"
        with self._lock:
            targets = list(self.token_usage_dirs)
        for directory in targets:
            path = directory / "turn_trace.jsonl"
            try:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(line)
                    handle.flush()
            except Exception:
                logger.exception("failed to append turn trace %s", path)

    def _append_token_turn(self, row: dict[str, Any]) -> None:
        line = json.dumps(row, ensure_ascii=False) + "\n"
        for directory in self.token_usage_dirs:
            path = directory / "turns.jsonl"
            try:
                with path.open("a", encoding="utf-8") as handle:
                    handle.write(line)
            except Exception:
                logger.exception("failed to append token usage %s", path)

    def _write_summary_task(self, summary: dict[str, Any]) -> None:
        text = json.dumps(summary, indent=2, ensure_ascii=False)
        for directory in self.token_usage_dirs:
            path = directory / "summary_task.json"
            try:
                path.write_text(text, encoding="utf-8")
            except Exception:
                logger.exception("failed to write summary_task %s", path)

    def _write_summary_session(self, summary: dict[str, Any]) -> None:
        text = json.dumps(summary, indent=2, ensure_ascii=False)
        for directory in self.token_usage_dirs:
            path = directory / "summary_session.json"
            try:
                path.write_text(text, encoding="utf-8")
            except Exception:
                logger.exception("failed to write summary_session %s", path)

    def _write_session(self, sid: str, snap: dict[str, Any]) -> None:
        if self.stats_dir is None:
            return
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in sid)[:120]
        path = self.stats_dir / "sessions" / f"{safe}.json"
        try:
            path.write_text(json.dumps(snap, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception:
            logger.exception("failed to write session stats %s", path)
