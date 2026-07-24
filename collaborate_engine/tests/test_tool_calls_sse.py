# SPDX-License-Identifier: Apache-2.0
"""tool_calls SSE passthrough tests."""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

from collaborate_engine.core.settings import CollaborativeSettings
from collaborate_engine.orchestrator import stream_collaborative_chat_completion


def _payloads(chunks: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in chunks:
        if not line.startswith("data: "):
            continue
        raw = line[6:].strip()
        if raw == "[DONE]":
            continue
        out.append(json.loads(raw))
    return out


@pytest.mark.asyncio
async def test_local_tool_calls_sse():
    class FakeSmall:
        async def stream_chat(self, **_kwargs: Any):
            yield SimpleNamespace(
                new_text="",
                finished=False,
                finish_reason=None,
                tool_calls=[
                    {
                        "index": 0,
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": "{"},
                    }
                ],
            )
            yield SimpleNamespace(
                new_text="",
                finished=True,
                finish_reason="tool_calls",
                tool_calls=[
                    {
                        "index": 0,
                        "function": {"arguments": '"path":"a.py"}'},
                    }
                ],
            )

    class FakeRemote:
        async def chat_completion_stream(self, *_a: Any, **_k: Any):
            if False:
                yield ""  # pragma: no cover
            raise AssertionError("remote should not be called")

    chunks: list[str] = []
    async for line in stream_collaborative_chat_completion(
        engine=FakeSmall(),
        messages=[{"role": "user", "content": "read"}],
        collab=CollaborativeSettings(
            run_mode="auto_offload",
            offload_tokens=["<|llm_offload|>"],
        ),
        remote_config=SimpleNamespace(model="l"),
        remote_client=FakeRemote(),
        stream_chat_kwargs={"messages": [{"role": "user", "content": "read"}]},
        remote_body={"model": "l"},
        exposed_model="pyrodash",
    ):
        chunks.append(line)

    payloads = _payloads(chunks)
    tool_deltas = [
        c["choices"][0]["delta"]["tool_calls"]
        for c in payloads
        if c.get("choices") and c["choices"][0].get("delta", {}).get("tool_calls")
    ]
    assert tool_deltas
    assert any(tc[0].get("id") == "call_1" for tc in tool_deltas)
    assert any(
        c["choices"][0].get("finish_reason") == "tool_calls" for c in payloads
    )


@pytest.mark.asyncio
async def test_remote_tool_calls_sse_after_offload():
    class FakeSmall:
        async def stream_chat(self, **_kwargs: Any):
            yield SimpleNamespace(
                new_text="go <|llm_offload|>",
                finished=False,
                finish_reason=None,
                tool_calls=None,
            )

    class FakeRemote:
        async def chat_completion_stream(self, _config: Any, body: dict[str, Any]):
            yield (
                'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_r",'
                '"type":"function","function":{"name":"search","arguments":"{}"}}]},'
                '"finish_reason":null}]}\n\n'
            )
            yield 'data: {"choices":[{"delta":{},"finish_reason":"tool_calls"}]}\n\n'
            yield "data: [DONE]\n\n"

    chunks: list[str] = []
    async for line in stream_collaborative_chat_completion(
        engine=FakeSmall(),
        messages=[{"role": "user", "content": "q"}],
        collab=CollaborativeSettings(
            run_mode="auto_offload",
            offload_tokens=["<|llm_offload|>"],
        ),
        remote_config=SimpleNamespace(model="l"),
        remote_client=FakeRemote(),
        stream_chat_kwargs={"messages": [{"role": "user", "content": "q"}]},
        remote_body={"model": "l"},
        exposed_model="pyrodash",
    ):
        chunks.append(line)

    joined = "".join(chunks)
    assert "call_r" in joined
    assert "tool_calls" in joined
    assert "<|llm_offload|>" not in joined
