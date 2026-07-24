# SPDX-License-Identifier: Apache-2.0
"""OpenAI-compatible SSE helpers."""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any


def parse_sse_payload(line: str) -> dict[str, Any] | None:
    stripped = line.strip()
    if not stripped.startswith("data: "):
        return None
    payload = stripped[6:].strip()
    if not payload or payload == "[DONE]":
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


async def iter_sse_lines(stream: AsyncIterator[str | bytes]) -> AsyncIterator[str]:
    buffer = ""
    async for raw in stream:
        piece = raw if isinstance(raw, str) else raw.decode("utf-8", errors="replace")
        buffer += piece
        while "\n" in buffer:
            line, _, buffer = buffer.partition("\n")
            line = line.rstrip("\r")
            if line.strip():
                yield line
    tail = buffer.rstrip("\r")
    if tail.strip():
        yield tail


def format_chat_delta_chunk(
    response_id: str,
    model_name: str,
    *,
    reasoning: str | None = None,
    content: str | None = None,
    tool_calls: list[dict[str, Any]] | None = None,
    finish_reason: str | None = None,
    role: str | None = None,
) -> str | None:
    if (
        not reasoning
        and not content
        and not tool_calls
        and finish_reason is None
        and role is None
    ):
        return None
    delta: dict[str, Any] = {}
    if role:
        delta["role"] = role
    if reasoning:
        delta["reasoning_content"] = reasoning
    if content:
        delta["content"] = content
    if tool_calls:
        delta["tool_calls"] = tool_calls
    chunk = {
        "id": response_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model_name,
        "choices": [
            {
                "index": 0,
                "delta": delta,
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"


def merge_tool_call_deltas(
    accumulated: dict[int, dict[str, Any]],
    delta_tool_calls: list[Any],
) -> dict[int, dict[str, Any]]:
    for tc in delta_tool_calls:
        if not isinstance(tc, dict):
            continue
        idx = int(tc.get("index", 0))
        if idx not in accumulated:
            accumulated[idx] = {
                "index": idx,
                "id": tc.get("id") or "",
                "type": tc.get("type") or "function",
                "function": {"name": "", "arguments": ""},
            }
        entry = accumulated[idx]
        if tc.get("id"):
            entry["id"] = tc["id"]
        if tc.get("type"):
            entry["type"] = tc["type"]
        fn = tc.get("function")
        if isinstance(fn, dict):
            if fn.get("name"):
                entry["function"]["name"] = fn["name"]
            if fn.get("arguments"):
                entry["function"]["arguments"] += fn["arguments"]
    return accumulated


def tool_calls_from_accumulated(
    accumulated: dict[int, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [accumulated[idx] for idx in sorted(accumulated)]
