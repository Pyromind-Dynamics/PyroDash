# SPDX-License-Identifier: Apache-2.0
"""Chat message helpers for collaborative decoding."""

from __future__ import annotations

from typing import Any

from .settings import DEFAULT_TOKEN_SAVING_PROMPT


def append_system_message(
    messages: list[dict[str, Any]], text: str
) -> list[dict[str, Any]]:
    """Append text to the first system message, or insert a new system message."""
    prompt = (text or "").strip()
    if not prompt:
        return messages
    out = [dict(m) for m in messages]
    for msg in out:
        if msg.get("role") == "system":
            existing = msg.get("content") or ""
            if isinstance(existing, list):
                existing = str(existing)
            msg["content"] = f"{existing}\n\n{prompt}".strip()
            return out
    out.insert(0, {"role": "system", "content": prompt})
    return out


def inject_token_saving_prompt(
    messages: list[dict[str, Any]], prompt: str | None
) -> list[dict[str, Any]]:
    text = (prompt or DEFAULT_TOKEN_SAVING_PROMPT).strip()
    if not text:
        return messages
    return append_system_message(messages, text)
