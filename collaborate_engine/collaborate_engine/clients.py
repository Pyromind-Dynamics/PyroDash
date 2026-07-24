# SPDX-License-Identifier: Apache-2.0
"""OpenAI-compatible HTTP clients for small and large model backends."""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

from .core.settings import EndpointConfig
from .sse import iter_sse_lines, parse_sse_payload


@dataclass
class StreamChunk:
    """Minimal local-engine chunk contract used by the orchestrator."""

    new_text: str = ""
    finished: bool = False
    finish_reason: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class OpenAICompatibleClient:
    """Thin async client for OpenAI-compatible ``/v1/chat/completions``."""

    def __init__(
        self,
        endpoint: EndpointConfig,
        *,
        timeout: float = 600.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.endpoint = endpoint
        self._timeout = timeout
        self._client = client
        self._owns_client = client is None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        key = (self.endpoint.api_key or "").strip()
        if key and key.upper() != "EMPTY":
            headers["Authorization"] = f"Bearer {key}"
        return headers

    async def chat_completion_stream(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        stop: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> AsyncIterator[str]:
        """Yield raw SSE lines from the upstream (including ``data:`` prefixes)."""
        body: dict[str, Any] = {
            "model": model or self.endpoint.model,
            "messages": messages,
            "stream": True,
        }
        if max_tokens is not None:
            body["max_tokens"] = max_tokens
        if temperature is not None:
            body["temperature"] = temperature
        if top_p is not None:
            body["top_p"] = top_p
        if stop:
            body["stop"] = stop
        if extra:
            body.update(extra)

        client = await self._get_client()
        async with client.stream(
            "POST",
            self.endpoint.chat_url(),
            headers=self._headers(),
            json=body,
        ) as response:
            response.raise_for_status()
            async for line in iter_sse_lines(response.aiter_bytes()):
                yield line if line.endswith("\n") else line + "\n"

    async def chat_completion_stream_as_engine(
        self,
        messages: list[dict[str, Any]],
        *,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        top_p: float | None = None,
        stop: list[str] | None = None,
        extra: dict[str, Any] | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Adapt OpenAI SSE into ``StreamChunk(new_text, finished)`` for orchestration."""
        async for line in self.chat_completion_stream(
            messages,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            top_p=top_p,
            stop=stop,
            extra=extra,
        ):
            stripped = line.strip()
            if stripped == "data: [DONE]":
                yield StreamChunk(new_text="", finished=True)
                return
            data = parse_sse_payload(stripped if stripped.startswith("data:") else f"data: {stripped}")
            if data is None:
                continue
            for choice in data.get("choices") or []:
                delta = choice.get("delta") or {}
                # Prefer content (often already contains <think>…</think>).
                # Fall back to reasoning_content for APIs that stream it alone.
                text = delta.get("content") or delta.get("reasoning_content") or ""
                tool_calls = delta.get("tool_calls")
                finish_reason = choice.get("finish_reason")
                finished = bool(finish_reason)
                if text or tool_calls or finished:
                    yield StreamChunk(
                        new_text=text or "",
                        finished=finished,
                        finish_reason=finish_reason,
                        tool_calls=tool_calls if isinstance(tool_calls, list) else None,
                    )
                if finished:
                    return


class SmallModelBackend:
    """Local (small) model backend satisfying the orchestrator ``engine`` contract."""

    def __init__(self, client: OpenAICompatibleClient) -> None:
        self._client = client

    async def stream_chat(self, **kwargs: Any) -> AsyncIterator[StreamChunk]:
        messages = kwargs.get("messages") or []
        async for chunk in self._client.chat_completion_stream_as_engine(
            messages,
            model=kwargs.get("model"),
            max_tokens=kwargs.get("max_tokens"),
            temperature=kwargs.get("temperature"),
            top_p=kwargs.get("top_p"),
            stop=kwargs.get("stop"),
            extra=kwargs.get("extra"),
        ):
            yield chunk


class LargeModelRemoteClient:
    """Remote (large) model backend yielding OpenAI SSE lines."""

    def __init__(self, client: OpenAICompatibleClient) -> None:
        self._client = client

    async def chat_completion_stream(
        self, config: Any, body: dict[str, Any]
    ) -> AsyncIterator[str]:
        model = getattr(config, "model", None) or body.get("model") or self._client.endpoint.model
        messages = body.get("messages") or []
        extra = {
            k: v
            for k, v in body.items()
            if k
            not in {
                "model",
                "messages",
                "stream",
                "max_tokens",
                "temperature",
                "top_p",
                "stop",
            }
        }
        async for line in self._client.chat_completion_stream(
            messages,
            model=model,
            max_tokens=body.get("max_tokens"),
            temperature=body.get("temperature"),
            top_p=body.get("top_p"),
            stop=body.get("stop"),
            extra=extra or None,
        ):
            # Ensure SSE framing for orchestrator parse.
            if line.startswith("data:"):
                yield line if line.endswith("\n\n") else line.rstrip("\n") + "\n\n"
            else:
                yield f"data: {line.strip()}\n\n"
