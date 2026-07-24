# SPDX-License-Identifier: Apache-2.0
"""Orchestrator tests with fake small/large backends."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from collaborate_engine.core.settings import CollaborativeSettings
from collaborate_engine.orchestrator import stream_collaborative_chat_completion


class FakeSmall:
    def __init__(self, pieces: list[tuple[str, bool]]):
        self.pieces = pieces

    async def stream_chat(self, **_kwargs: Any):
        for text, finished in self.pieces:
            yield SimpleNamespace(new_text=text, finished=finished)


class FakeRemote:
    def __init__(self, lines: list[str]):
        self.lines = lines
        self.last_body: dict[str, Any] | None = None

    async def chat_completion_stream(self, _config: Any, body: dict[str, Any]):
        self.last_body = body
        for line in self.lines:
            yield line


@pytest.mark.asyncio
async def test_local_direct_no_offload():
    engine = FakeSmall([("hello world", True)])
    remote = FakeRemote([])
    chunks: list[str] = []
    async for line in stream_collaborative_chat_completion(
        engine=engine,
        messages=[{"role": "user", "content": "hi"}],
        collab=CollaborativeSettings(
            run_mode="auto_offload",
            local_model="s",
            remote_model="l",
            offload_tokens=["<|llm_offload|>"],
        ),
        remote_config=SimpleNamespace(model="l"),
        remote_client=remote,
        stream_chat_kwargs={"messages": [{"role": "user", "content": "hi"}]},
        remote_body={"model": "l"},
        exposed_model="pyrodash",
    ):
        chunks.append(line)
    joined = "".join(chunks)
    assert "hello world" in joined
    assert remote.last_body is None
    assert chunks[-1].strip() == "data: [DONE]"


@pytest.mark.asyncio
async def test_offload_then_remote():
    engine = FakeSmall([("partial <|llm_offload|>", False)])
    remote = FakeRemote(
        [
            'data: {"choices":[{"delta":{"content":" from-large"},"finish_reason":null}]}\n\n',
            "data: [DONE]\n\n",
        ]
    )
    chunks: list[str] = []
    async for line in stream_collaborative_chat_completion(
        engine=engine,
        messages=[{"role": "user", "content": "q"}],
        collab=CollaborativeSettings(
            run_mode="auto_offload",
            local_model="s",
            remote_model="l",
            offload_tokens=["<|llm_offload|>"],
        ),
        remote_config=SimpleNamespace(model="l"),
        remote_client=remote,
        stream_chat_kwargs={"messages": [{"role": "user", "content": "q"}]},
        remote_body={"model": "l"},
        exposed_model="pyrodash",
    ):
        chunks.append(line)

    joined = "".join(chunks)
    assert "partial" in joined
    assert "<|llm_offload|>" not in joined
    assert " from-large" in joined
    assert remote.last_body is not None
    assert any(m.get("role") == "system" for m in remote.last_body["messages"])
    assert any(
        m.get("role") == "assistant" and "partial" in (m.get("content") or "")
        for m in remote.last_body["messages"]
    )
