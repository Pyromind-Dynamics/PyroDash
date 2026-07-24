# SPDX-License-Identifier: Apache-2.0
"""Collaborative orchestration: small model until offload, then large model."""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

from .core.handoff import build_remote_messages
from .core.offload_detector import OffloadDetector
from .core.settings import CollaborativeSettings
from .core.thinking import ThinkingParser
from .local_stream import (
    drain_thinking_parser_at_offload,
    flush_thinking_parser_chunks,
    yield_thinking_parser_chunks,
)
from .sse import format_chat_delta_chunk, iter_sse_lines, parse_sse_payload

logger = logging.getLogger(__name__)

FormatDelta = Callable[..., str | None]


async def stream_collaborative_chat_completion(
    *,
    engine: Any,
    messages: list[dict[str, Any]],
    collab: CollaborativeSettings,
    remote_config: Any,
    remote_client: Any,
    stream_chat_kwargs: dict[str, Any],
    remote_body: dict[str, Any],
    exposed_model: str,
    format_delta: FormatDelta = format_chat_delta_chunk,
    on_event: Callable[[str, dict[str, Any]], None] | None = None,
) -> AsyncIterator[str]:
    """Stream small-model output until offload, then continue on the large model.

    Offload trigger tokens are never forwarded to the client.
    Upstream ``tool_calls`` deltas are re-emitted as OpenAI SSE chunks.
    """

    def _emit(event: str, **payload: Any) -> None:
        if on_event is not None:
            on_event(event, payload)

    response_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
    model_name = exposed_model
    detector = OffloadDetector(collab.offload_tokens)
    thinking_parser = ThinkingParser()
    local_partial = ""
    local_finish_reason: str | None = None
    saw_local_tool_calls = False

    role_line = format_delta(response_id, model_name, role="assistant")
    if role_line:
        yield role_line

    async for output in engine.stream_chat(**stream_chat_kwargs):
        new_text = getattr(output, "new_text", None) or ""
        finished = bool(getattr(output, "finished", False))
        finish_reason = getattr(output, "finish_reason", None)
        tool_calls = getattr(output, "tool_calls", None)

        # Forward structured tool_calls from the small model as OpenAI chunks.
        if tool_calls and not detector.triggered:
            saw_local_tool_calls = True
            out_line = format_delta(
                response_id, model_name, tool_calls=tool_calls
            )
            if out_line:
                yield out_line

        if not new_text:
            if finished and not detector.triggered:
                tail = detector.flush()
                if tail:
                    local_partial += tail
                    for line in yield_thinking_parser_chunks(
                        response_id,
                        model_name,
                        thinking_parser,
                        tail,
                        format_delta=format_delta,
                    ):
                        yield line
                local_finish_reason = finish_reason
                break
            continue

        emit, hit = detector.feed(new_text)
        if emit:
            local_partial += emit
            for line in yield_thinking_parser_chunks(
                response_id,
                model_name,
                thinking_parser,
                emit,
                format_delta=format_delta,
            ):
                yield line

        if hit:
            for line in drain_thinking_parser_at_offload(
                response_id,
                model_name,
                thinking_parser,
                format_delta=format_delta,
            ):
                yield line
            _emit(
                "local_offload",
                response_id=response_id,
                local_partial=local_partial,
                matched_token=detector.matched_token,
            )
            break

        if finished and not detector.triggered:
            tail = detector.flush()
            if tail:
                local_partial += tail
                for line in yield_thinking_parser_chunks(
                    response_id,
                    model_name,
                    thinking_parser,
                    tail,
                    format_delta=format_delta,
                ):
                    yield line
            local_finish_reason = finish_reason
            break

    if not detector.triggered:
        for line in flush_thinking_parser_chunks(
            response_id,
            model_name,
            thinking_parser,
            format_delta=format_delta,
        ):
            yield line
        _emit("local_direct", response_id=response_id, local_partial=local_partial)
        if saw_local_tool_calls and not local_finish_reason:
            local_finish_reason = "tool_calls"
        final = format_delta(
            response_id,
            model_name,
            finish_reason=local_finish_reason or "stop",
        )
        if final:
            yield final
        yield "data: [DONE]\n\n"
        return

    remote_messages = build_remote_messages(messages, local_partial)
    body = dict(remote_body)
    body["messages"] = remote_messages
    body["stream"] = True

    _emit(
        "remote_request",
        response_id=response_id,
        remote_messages=remote_messages,
    )

    try:
        async for line in iter_sse_lines(
            remote_client.chat_completion_stream(remote_config, body)
        ):
            if line.strip() == "data: [DONE]":
                continue
            data = parse_sse_payload(line)
            if data is None:
                continue
            if data.get("usage"):
                continue
            for choice in data.get("choices") or []:
                delta = choice.get("delta") or {}
                content = delta.get("content")
                reasoning = delta.get("reasoning_content")
                remote_tool_calls = delta.get("tool_calls")
                finish_reason = choice.get("finish_reason")
                out_line = format_delta(
                    response_id,
                    model_name,
                    reasoning=reasoning,
                    content=content,
                    tool_calls=remote_tool_calls,
                    finish_reason=finish_reason,
                )
                if out_line:
                    yield out_line
    except Exception as exc:
        message = getattr(exc, "message", None) or str(exc)
        error_data = {"error": {"message": message, "type": "upstream_error"}}
        yield f"data: {json.dumps(error_data)}\n\n"
        _emit("remote_error", response_id=response_id, message=message)
        yield "data: [DONE]\n\n"
        return

    _emit("remote_offload", response_id=response_id)
    yield "data: [DONE]\n\n"
