# SPDX-License-Identifier: Apache-2.0
"""User-facing Collaborate Engine: dual OpenAI APIs in → one chat API out."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from .clients import (
    LargeModelRemoteClient,
    OpenAICompatibleClient,
    SmallModelBackend,
)
from .core.messages import append_system_message
from .core.settings import (
    DEFAULT_OFFLOAD_TOKENS,
    EndpointConfig,
    EngineConfig,
    CollaborativeSettings,
    RunMode,
    collaborative_local_system_append,
)
from .non_stream import collaborative_chat_completion_non_stream
from .orchestrator import stream_collaborative_chat_completion
from .sse import parse_sse_payload


class CollaborateEngine:
    """Give small + large model API endpoints; call ``chat_completions`` like OpenAI.

    Example::

        engine = CollaborateEngine(
            small_base_url="http://127.0.0.1:8001/v1",
            small_model="PyroDash-4B",
            large_base_url="https://api.example.com/v1",
            large_api_key="sk-...",
            large_model="glm-...",
        )
        resp = await engine.chat_completions(
            messages=[{"role": "user", "content": "1+1=?"}],
        )
        print(resp["choices"][0]["message"]["content"])
    """

    def __init__(
        self,
        *,
        small_base_url: str,
        small_model: str,
        large_base_url: str,
        large_model: str,
        small_api_key: str = "EMPTY",
        large_api_key: str = "EMPTY",
        exposed_model_name: str = "pyrodash",
        run_mode: RunMode = "auto_offload",
        offload_tokens: list[str] | None = None,
        global_max_tokens: int = 8192,
        timeout: float = 600.0,
    ) -> None:
        self.config = EngineConfig(
            small=EndpointConfig(
                base_url=small_base_url,
                api_key=small_api_key,
                model=small_model,
            ),
            large=EndpointConfig(
                base_url=large_base_url,
                api_key=large_api_key,
                model=large_model,
            ),
            exposed_model_name=exposed_model_name,
            run_mode=run_mode,
            offload_tokens=list(offload_tokens)
            if offload_tokens is not None
            else list(DEFAULT_OFFLOAD_TOKENS),
            global_max_tokens=global_max_tokens,
        )
        self.collab = self.config.to_collab_settings()
        self._small = OpenAICompatibleClient(self.config.small, timeout=timeout)
        self._large = OpenAICompatibleClient(self.config.large, timeout=timeout)
        self._engine = SmallModelBackend(self._small)
        self._remote = LargeModelRemoteClient(self._large)

    async def aclose(self) -> None:
        await self._small.aclose()
        await self._large.aclose()

    async def __aenter__(self) -> CollaborateEngine:
        return self

    async def __aexit__(self, *args: Any) -> None:
        await self.aclose()

    def _prepare(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int | None,
        temperature: float | None,
        top_p: float | None,
        stop: str | list[str] | None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
        base_messages = [dict(m) for m in messages]
        local_messages = list(base_messages)
        append = collaborative_local_system_append(self.collab)
        if append:
            local_messages = append_system_message(local_messages, append)

        if max_tokens is None:
            max_tokens = self.config.global_max_tokens
        if isinstance(stop, str):
            stop = [stop]

        stream_chat_kwargs: dict[str, Any] = {
            "messages": local_messages,
            "model": self.config.small.model,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            stream_chat_kwargs["temperature"] = temperature
        if top_p is not None:
            stream_chat_kwargs["top_p"] = top_p
        if stop:
            stream_chat_kwargs["stop"] = stop

        remote_body: dict[str, Any] = {
            "model": self.config.large.model,
            "max_tokens": max_tokens,
        }
        if temperature is not None:
            remote_body["temperature"] = temperature
        if top_p is not None:
            remote_body["top_p"] = top_p

        return base_messages, stream_chat_kwargs, remote_body

    async def chat_completions(
        self,
        *,
        messages: list[dict[str, Any]],
        stream: bool = False,
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        stop: str | list[str] | None = None,
        **_ignored: Any,
    ) -> dict[str, Any] | AsyncIterator[dict[str, Any]]:
        """OpenAI-shaped chat completions.

        - ``stream=False`` → one ``chat.completion`` dict
        - ``stream=True`` → async iterator of ``chat.completion.chunk`` dicts
          (no ``[DONE]`` sentinel; iterator simply ends)
        """
        base_messages, stream_chat_kwargs, remote_body = self._prepare(
            messages,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop,
        )
        exposed = self.config.exposed_model_name

        if stream:
            return self._stream(
                base_messages=base_messages,
                stream_chat_kwargs=stream_chat_kwargs,
                remote_body=remote_body,
                exposed=exposed,
            )

        return await collaborative_chat_completion_non_stream(
            engine=self._engine,
            messages=base_messages,
            collab=self.collab,
            remote_config=self.config.large,
            remote_client=self._remote,
            stream_chat_kwargs=stream_chat_kwargs,
            remote_body=remote_body,
            exposed_model=exposed,
        )

    async def _stream(
        self,
        *,
        base_messages: list[dict[str, Any]],
        stream_chat_kwargs: dict[str, Any],
        remote_body: dict[str, Any],
        exposed: str,
    ) -> AsyncIterator[dict[str, Any]]:
        async for line in stream_collaborative_chat_completion(
            engine=self._engine,
            messages=base_messages,
            collab=self.collab,
            remote_config=self.config.large,
            remote_client=self._remote,
            stream_chat_kwargs=stream_chat_kwargs,
            remote_body=remote_body,
            exposed_model=exposed,
        ):
            data = parse_sse_payload(line)
            if data is not None:
                yield data
