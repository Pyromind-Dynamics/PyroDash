"""OpenAI-compatible chat.completions client."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import requests

from .offload import normalize_openai_tools, parse_openai_tool_calls

_RESERVED_SAMPLING_KEYS = frozenset({"extra_body"})


def _merge_sampling_value(body: dict[str, Any], key: str, val: Any) -> None:
    if (
        key == "chat_template_kwargs"
        and isinstance(body.get("chat_template_kwargs"), dict)
        and isinstance(val, dict)
    ):
        merged = dict(body["chat_template_kwargs"])
        merged.update(val)
        body[key] = merged
    else:
        body[key] = val


def apply_sampling(body: dict[str, Any], sampling: dict[str, Any] | None) -> None:
    """Overlay sampling dict onto the request body.

    Any key from the YAML/config is forwarded (not a fixed allowlist). Nested
    ``extra_body`` is flattened into the same JSON body (vLLM style).
    """
    if not sampling:
        return
    extra_body = sampling.get("extra_body")
    if isinstance(extra_body, dict):
        for key, val in extra_body.items():
            if val is None:
                continue
            _merge_sampling_value(body, key, val)
    for key, val in sampling.items():
        if key in _RESERVED_SAMPLING_KEYS or val is None:
            continue
        _merge_sampling_value(body, key, val)


@dataclass(frozen=True)
class EndpointConfig:
    base_url: str
    api_key: str
    model: str

    def normalized_base(self) -> str:
        return self.base_url.rstrip("/")


def call_openai_chat_sync(
    endpoint: EndpointConfig,
    messages: list[dict[str, Any]],
    *,
    max_tokens: int | None = None,
    tools: list[dict[str, Any]] | None = None,
    stop: list[str] | None = None,
    stop_token_ids: list[int] | None = None,
    skip_special_tokens: bool | None = None,
    temperature: float | None = None,
    sampling: dict[str, Any] | None = None,
    enable_thinking: bool | None = None,
    reasoning_effort: str | None = None,
    timeout: float = 600.0,
) -> tuple[str, str, dict[str, Any] | None, list[dict[str, Any]]]:
    if max_tokens is not None and max_tokens <= 0:
        return "[Error: max_tokens <= 0]", "", None, []
    if not endpoint.api_key:
        return "[Error: api_key not set]", "", None, []

    url = f"{endpoint.normalized_base()}/chat/completions"
    headers = {
        "Authorization": f"Bearer {endpoint.api_key}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "model": endpoint.model,
        "messages": messages,
    }
    if max_tokens is not None:
        body["max_tokens"] = max_tokens
    if temperature is not None and not sampling:
        body["temperature"] = temperature
    if stop_token_ids:
        body["stop_token_ids"] = list(stop_token_ids)
    elif stop:
        body["stop"] = stop
    if skip_special_tokens is not None:
        body["skip_special_tokens"] = bool(skip_special_tokens)
    openai_tools = normalize_openai_tools(tools)
    if openai_tools:
        body["tools"] = openai_tools
    if enable_thinking is not None:
        chat_kwargs: dict[str, Any] = {"enable_thinking": bool(enable_thinking)}
        if enable_thinking and reasoning_effort:
            chat_kwargs["reasoning_effort"] = reasoning_effort
            body["reasoning_effort"] = reasoning_effort
        body["chat_template_kwargs"] = chat_kwargs
    apply_sampling(body, sampling)

    try:
        response = requests.post(url, headers=headers, json=body, timeout=timeout)
        if response.status_code != 200:
            return f"[Error: status {response.status_code}: {response.text[:400]}]", "", None, []
        data = response.json()
        message = data["choices"][0].get("message", {})
        think = str(message.get("reasoning") or message.get("reasoning_content") or "")
        content = str(message.get("content") or "")
        tool_calls = parse_openai_tool_calls(message.get("tool_calls"))
        usage = data.get("usage")
        if usage is not None and not isinstance(usage, dict):
            usage = None
        return content, think, usage, tool_calls
    except Exception as exc:
        return f"[Error: remote call failed: {exc}]", "", None, []


async def call_openai_chat(*args, **kwargs):
    return await asyncio.to_thread(call_openai_chat_sync, *args, **kwargs)
