# SPDX-License-Identifier: Apache-2.0
"""Streaming detection of offload trigger tokens."""

from __future__ import annotations


class OffloadDetector:
    """Detect configured tokens in a streaming text buffer."""

    def __init__(self, tokens: list[str]) -> None:
        self.tokens = [t for t in tokens if t]
        self._pending = ""
        self.triggered = False
        self.matched_token: str | None = None

    @property
    def max_token_len(self) -> int:
        if not self.tokens:
            return 0
        return max(len(t) for t in self.tokens)

    def feed(self, chunk: str) -> tuple[str, bool]:
        """Return text safe to emit to the client and whether offload fired."""
        if self.triggered or not chunk:
            return ("", False)

        self._pending += chunk
        for token in self.tokens:
            idx = self._pending.find(token)
            if idx >= 0:
                before = self._pending[:idx]
                self.triggered = True
                self.matched_token = token
                self._pending = ""
                return (before, True)

        keep = max(0, self.max_token_len - 1)
        if keep == 0:
            emit, self._pending = self._pending, ""
            return (emit, False)

        if len(self._pending) <= keep:
            return ("", False)

        emit = self._pending[:-keep]
        self._pending = self._pending[-keep:]
        return (emit, False)

    def flush(self) -> str:
        """Emit any remaining buffered text when generation ends without offload."""
        if self.triggered:
            return ""
        rest = self._pending
        self._pending = ""
        return rest
