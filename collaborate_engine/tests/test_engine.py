# SPDX-License-Identifier: Apache-2.0
"""CollaborateEngine API smoke tests with fake backends."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from collaborate_engine.engine import CollaborateEngine


class FakeSmall:
    async def stream_chat(self, **_kwargs: Any):
        yield SimpleNamespace(new_text="ok <|llm_offload|>", finished=False)


class FakeRemote:
    async def chat_completion_stream(self, _config: Any, body: dict[str, Any]):
        assert body["messages"]
        yield 'data: {"choices":[{"delta":{"content":"done"},"finish_reason":"stop"}]}\n\n'
        yield "data: [DONE]\n\n"


@pytest.mark.asyncio
async def test_chat_completions_non_stream(monkeypatch):
    engine = CollaborateEngine(
        small_base_url="http://small/v1",
        small_model="s",
        large_base_url="http://large/v1",
        large_model="l",
    )
    engine._engine = FakeSmall()
    engine._remote = FakeRemote()

    resp = await engine.chat_completions(
        messages=[{"role": "user", "content": "hi"}],
    )
    content = resp["choices"][0]["message"]["content"]
    assert "ok" in content
    assert "done" in content
    assert "<|llm_offload|>" not in content
    await engine.aclose()


@pytest.mark.asyncio
async def test_chat_completions_stream():
    engine = CollaborateEngine(
        small_base_url="http://small/v1",
        small_model="s",
        large_base_url="http://large/v1",
        large_model="l",
    )
    engine._engine = FakeSmall()
    engine._remote = FakeRemote()

    stream = await engine.chat_completions(
        messages=[{"role": "user", "content": "hi"}],
        stream=True,
    )
    texts: list[str] = []
    async for chunk in stream:
        delta = chunk["choices"][0].get("delta") or {}
        if delta.get("content"):
            texts.append(delta["content"])
    joined = "".join(texts)
    assert "ok" in joined and "done" in joined
    await engine.aclose()
