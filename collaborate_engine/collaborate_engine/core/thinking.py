# SPDX-License-Identifier: Apache-2.0
"""Streaming and non-streaming <think>...</think> parsers."""

from __future__ import annotations

import re
from typing import List, Tuple

_OPEN_TAG = "<think>"
_CLOSE_TAG = "</think>"
_OPEN_LEN = len(_OPEN_TAG)
_CLOSE_LEN = len(_CLOSE_TAG)
_MINIMAX_OPEN_TAG = "<mm:think>"
_MINIMAX_CLOSE_TAG = "</mm:think>"

_THINKING_PATTERN = re.compile(r"<think>(.*?)</think>", re.DOTALL)
_THINKING_TAIL_PATTERN = re.compile(r"^(.*?)</think>", re.DOTALL)


def extract_thinking(text: str) -> Tuple[str, str]:
    if not text:
        return ("", "")

    text = text.replace(_MINIMAX_OPEN_TAG, _OPEN_TAG).replace(
        _MINIMAX_CLOSE_TAG, _CLOSE_TAG
    )

    thinking_parts = []
    remaining = text

    while True:
        match = _THINKING_PATTERN.search(remaining)
        if not match:
            break
        thinking_parts.append(match.group(1))
        remaining = remaining[: match.start()] + remaining[match.end() :]

    if thinking_parts:
        thinking = "\n".join(thinking_parts).strip()
        return (thinking, remaining.strip())

    if "</think>" in text and "<think>" not in text:
        match = _THINKING_TAIL_PATTERN.match(text)
        if match:
            thinking = match.group(1).strip()
            remaining = text[match.end() :].strip()
            return (thinking, remaining)

    if "<think>" in text and "</think>" not in text:
        idx = text.index("<think>")
        before = text[:idx]
        after = text[idx + _OPEN_LEN :]
        return ("", (before + after).strip())

    return ("", text)


class ThinkingParser:
    """Stateful streaming parser for separating <think>...</think> from content."""

    def __init__(self, start_in_thinking: bool = False):
        self._in_thinking: bool = start_in_thinking
        self._buffer: str = ""
        self._close_seen: bool = False
        self._thinking_accumulated: List[str] = []
        self._content_emitted: bool = False

    def feed(self, text: str) -> Tuple[str, str]:
        if not text:
            return ("", "")

        text = self._buffer + text
        self._buffer = ""

        thinking_out = []
        content_out = []

        i = 0
        while i < len(text):
            if text[i] == "<":
                remaining = text[i:]

                if remaining.startswith(_OPEN_TAG):
                    self._in_thinking = True
                    i += _OPEN_LEN
                    continue

                if remaining.startswith(_CLOSE_TAG):
                    self._in_thinking = False
                    self._close_seen = True
                    i += _CLOSE_LEN
                    continue

                if self._could_be_tag(remaining):
                    self._buffer = remaining
                    break

                if self._in_thinking:
                    thinking_out.append("<")
                else:
                    content_out.append("<")
                i += 1
            else:
                if self._in_thinking:
                    thinking_out.append(text[i])
                else:
                    content_out.append(text[i])
                i += 1

        thinking_delta = "".join(thinking_out)
        content_delta = "".join(content_out)
        if thinking_delta:
            self._thinking_accumulated.append(thinking_delta)
        if content_delta:
            self._content_emitted = True
        return (thinking_delta, content_delta)

    def finish(self) -> Tuple[str, str]:
        partial = self._buffer
        self._buffer = ""

        if (
            self._in_thinking
            and not self._close_seen
            and not self._content_emitted
            and self._thinking_accumulated
        ):
            recovered = "".join(self._thinking_accumulated) + partial
            self._content_emitted = True
            return ("", recovered)

        if not partial:
            return ("", "")

        if self._in_thinking:
            self._thinking_accumulated.append(partial)
            return (partial, "")
        self._content_emitted = True
        return ("", partial)

    @staticmethod
    def _could_be_tag(text: str) -> bool:
        length = len(text)
        if length >= _CLOSE_LEN:
            return False
        if _OPEN_TAG[:length] == text:
            return True
        if _CLOSE_TAG[:length] == text:
            return True
        return False
