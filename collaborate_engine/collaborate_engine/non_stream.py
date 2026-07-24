# SPDX-License-Identifier: Apache-2.0
"""Non-streaming collaborative chat completion (accumulates SSE)."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from .core.settings import CollaborativeSettings
from .orchestrator import stream_collaborative_chat_completion
from .sse import merge_tool_call_deltas, tool_calls_from_accumulated


async def collaborative_chat_completion_non_stream(
    *,
    engine: Any,
    messages: list[dict[str, Any]],
    collab: CollaborativeSettings,
    remote_config: Any,
    remote_client: Any,
    stream_chat_kwargs: dict[str, Any],
    remote_body: dict[str, Any],
    exposed_model: str,
    **stream_kwargs: Any,
) -> dict[str, Any]:
    content_parts: list[str] = []
    reasoning_parts: list[str] = []
    tool_calls_acc: dict[int, dict[str, Any]] = {}
    finish_reason = "stop"

    async for line in stream_collaborative_chat_completion(
        engine=engine,
        messages=messages,
        collab=collab,
        remote_config=remote_config,
        remote_client=remote_client,
        stream_chat_kwargs=stream_chat_kwargs,
        remote_body=remote_body,
        exposed_model=exposed_model,
        **stream_kwargs,
    ):
        if not line.startswith("data: "):
            continue
        payload = line[6:].strip()
        if payload == "[DONE]":
            break
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            continue
        if "error" in data:
            raise RuntimeError(data["error"].get("message", "upstream error"))
        for choice in data.get("choices") or []:
            delta = choice.get("delta") or {}
            content = delta.get("content")
            reasoning = delta.get("reasoning_content")
            delta_tool_calls = delta.get("tool_calls")
            choice_finish = choice.get("finish_reason")
            if choice_finish:
                finish_reason = choice_finish
            if content:
                content_parts.append(content)
            if reasoning:
                reasoning_parts.append(reasoning)
            if delta_tool_calls:
                merge_tool_call_deltas(tool_calls_acc, delta_tool_calls)

    message: dict[str, Any] = {"role": "assistant"}
    content_text = "".join(content_parts)
    if content_text:
        message["content"] = content_text
    elif not tool_calls_acc:
        message["content"] = ""
    if reasoning_parts:
        message["reasoning_content"] = "".join(reasoning_parts)
    if tool_calls_acc:
        message["tool_calls"] = tool_calls_from_accumulated(tool_calls_acc)
        if finish_reason == "stop":
            finish_reason = "tool_calls"

    return {
        "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": exposed_model,
        "choices": [
            {
                "index": 0,
                "message": message,
                "finish_reason": finish_reason,
            }
        ],
    }
