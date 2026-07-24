# SPDX-License-Identifier: Apache-2.0
"""Local-phase thinking/content streaming helpers."""

from __future__ import annotations

from collections.abc import Callable

from .core.thinking import ThinkingParser

FormatDelta = Callable[..., str | None]


def yield_thinking_parser_chunks(
    response_id: str,
    model_name: str,
    parser: ThinkingParser,
    text: str,
    *,
    format_delta: FormatDelta,
) -> list[str]:
    thinking_delta, content_delta = parser.feed(text)
    chunks: list[str] = []
    if thinking_delta:
        line = format_delta(response_id, model_name, reasoning=thinking_delta)
        if line:
            chunks.append(line)
    if content_delta:
        line = format_delta(response_id, model_name, content=content_delta)
        if line:
            chunks.append(line)
    return chunks


def drain_thinking_parser_at_offload(
    response_id: str,
    model_name: str,
    parser: ThinkingParser,
    *,
    format_delta: FormatDelta,
) -> list[str]:
    chunks: list[str] = []
    if parser._buffer:
        if parser._in_thinking:
            line = format_delta(response_id, model_name, reasoning=parser._buffer)
        else:
            line = format_delta(response_id, model_name, content=parser._buffer)
        if line:
            chunks.append(line)
        parser._buffer = ""
    return chunks


def flush_thinking_parser_chunks(
    response_id: str,
    model_name: str,
    parser: ThinkingParser,
    *,
    format_delta: FormatDelta,
) -> list[str]:
    thinking_delta, content_delta = parser.finish()
    chunks: list[str] = []
    if thinking_delta:
        line = format_delta(response_id, model_name, reasoning=thinking_delta)
        if line:
            chunks.append(line)
    if content_delta:
        line = format_delta(response_id, model_name, content=content_delta)
        if line:
            chunks.append(line)
    return chunks
