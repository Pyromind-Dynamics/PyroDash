"""Aggregate SLM/LLM token + offload counters for the math adapter."""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def normalize_usage(usage: dict[str, Any] | None) -> dict[str, int] | None:
    if not usage:
        return None
    p = usage.get("prompt_tokens")
    if p is None:
        p = usage.get("input_tokens")
    c = usage.get("completion_tokens")
    if c is None:
        c = usage.get("output_tokens")
    t = usage.get("total_tokens")
    if p is None and c is None and t is None:
        return None
    p, c = int(p or 0), int(c or 0)
    return {
        "prompt_tokens": p,
        "completion_tokens": c,
        "total_tokens": int(t) if t is not None else p + c,
    }


@dataclass
class MathStats:
    requests: int = 0
    offload_count: int = 0
    slm_prompt_tokens: int = 0
    slm_completion_tokens: int = 0
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0
    errors: int = 0
    started_at: float = field(default_factory=time.time)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(
        self,
        *,
        has_offload: bool,
        slm_usage: dict[str, int] | None,
        llm_usage: dict[str, int] | None,
        error: bool = False,
    ) -> None:
        with self._lock:
            self.requests += 1
            if error:
                self.errors += 1
            if has_offload:
                self.offload_count += 1
            if slm_usage:
                self.slm_prompt_tokens += int(slm_usage.get("prompt_tokens", 0))
                self.slm_completion_tokens += int(slm_usage.get("completion_tokens", 0))
            if llm_usage:
                self.llm_prompt_tokens += int(llm_usage.get("prompt_tokens", 0))
                self.llm_completion_tokens += int(llm_usage.get("completion_tokens", 0))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "requests": self.requests,
                "offload_count": self.offload_count,
                "offload_rate": self.offload_count / max(self.requests, 1),
                "slm_prompt_tokens": self.slm_prompt_tokens,
                "slm_completion_tokens": self.slm_completion_tokens,
                "llm_prompt_tokens": self.llm_prompt_tokens,
                "llm_completion_tokens": self.llm_completion_tokens,
                "errors": self.errors,
                "uptime_s": time.time() - self.started_at,
            }

    def persist(self, stats_dir: Path | None) -> None:
        if not stats_dir:
            return
        stats_dir.mkdir(parents=True, exist_ok=True)
        path = stats_dir / "summary.json"
        path.write_text(json.dumps(self.snapshot(), ensure_ascii=False, indent=2), encoding="utf-8")
