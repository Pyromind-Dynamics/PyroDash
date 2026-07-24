# SPDX-License-Identifier: Apache-2.0
"""Remote handoff formatting for collaborative thinking blocks."""

from __future__ import annotations

from typing import Any

from .messages import append_system_message
from .thinking import ThinkingParser

PART_THINK_OPEN = "<part_think>"
PART_THINK_CLOSE = "</part_think>"

DEFAULT_REMOTE_HANDOFF_PROMPT = (
    "Collaborative handoff protocol:\n"
    "- The assistant message may contain <part_think>...</part_think> blocks. "
    "Each block holds partial reasoning produced by a smaller local model "
    "before the task was offloaded to you.\n"
    "- Read the text inside <part_think> and continue that reasoning in your "
    "reasoning channel until you reach a final answer.\n"
    "- Put the user-facing answer only in normal assistant content. Do not "
    "repeat or quote the <part_think> text verbatim in the final answer.\n"
    "- <part_think> is an internal handoff marker, not user input. Never "
    "mention or explain this tag to the user."
)


def inject_remote_handoff_prompt(
    messages: list[dict[str, Any]], prompt: str | None
) -> list[dict[str, Any]]:
    text = (prompt or DEFAULT_REMOTE_HANDOFF_PROMPT).strip()
    if not text:
        return messages
    return append_system_message(messages, text)


def split_local_partial(text: str) -> tuple[str, str]:
    if not text:
        return ("", "")

    parser = ThinkingParser()
    _, content_delta = parser.feed(text)

    if parser._in_thinking and not parser._close_seen:
        thinking_body = "".join(parser._thinking_accumulated)
        if parser._buffer:
            thinking_body += parser._buffer
        return (thinking_body.strip(), (content_delta or "").strip())

    finish_thinking, finish_content = parser.finish()
    thinking_body = "".join(parser._thinking_accumulated) + (finish_thinking or "")
    answer_prefix = (content_delta or "") + (finish_content or "")
    return (thinking_body.strip(), answer_prefix.strip())


def format_remote_assistant_content(local_partial: str) -> str:
    thinking_body, answer_prefix = split_local_partial(local_partial)
    parts: list[str] = []
    if thinking_body:
        parts.append(f"{PART_THINK_OPEN}{thinking_body}{PART_THINK_CLOSE}")
    if answer_prefix:
        parts.append(answer_prefix)
    if parts:
        return "\n".join(parts)
    return local_partial.strip()


def build_remote_messages(
    base_messages: list[dict[str, Any]], local_partial: str
) -> list[dict[str, Any]]:
    messages = [dict(m) for m in base_messages]
    assistant_content = format_remote_assistant_content(local_partial)
    if assistant_content:
        messages.append({"role": "assistant", "content": assistant_content})
    messages = inject_remote_handoff_prompt(messages, DEFAULT_REMOTE_HANDOFF_PROMPT)
    return messages
