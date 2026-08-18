from __future__ import annotations

from typing import Any

import httpx

from app.config import Settings
from app.models import ChatCompletionRequest, ChatMessage, PyroDashUsage, TokenUsage

OFFLOAD_TOKEN = "<|llm_offload|>"

HANDOFF_SYSTEM_PROMPT = (
    "You are completing a task that a smaller model partially solved. "
    "Continue from the unresolved step without repeating the partial reasoning. "
    "Return only the user-facing completion."
)


class UpstreamError(RuntimeError):
    pass


class CollaborateEngine:
    def __init__(self, settings: Settings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self.client = client

    async def complete(
        self, request: ChatCompletionRequest
    ) -> tuple[str, str, PyroDashUsage]:
        slm_data = await self._call_slm(request)
        slm_reasoning, slm_content = _message_parts(slm_data)
        slm_text = slm_reasoning + slm_content
        slm_usage = _usage(slm_data.get("usage"))

        if OFFLOAD_TOKEN not in slm_text:
            finish_reason = _finish_reason(slm_data)
            return _render_message(slm_reasoning, slm_content), finish_reason, PyroDashUsage(
                offloaded=False,
                slm=slm_usage,
            )

        partial = slm_text.split(OFFLOAD_TOKEN, 1)[0]
        remaining_tokens = max(1, request.max_tokens - slm_usage.completion_tokens)
        llm_data = await self._call_glm(request.messages, partial, remaining_tokens)
        llm_reasoning, llm_content = _message_parts(llm_data)
        llm_usage = _usage(llm_data.get("usage"))
        combined_reasoning = _strip_think_tags(partial) + _strip_think_tags(llm_reasoning)

        return _render_message(combined_reasoning, llm_content), _finish_reason(llm_data), PyroDashUsage(
            offloaded=True,
            slm=slm_usage,
            llm=llm_usage,
        )

    async def _call_slm(self, request: ChatCompletionRequest) -> dict[str, Any]:
        body = {
            "model": self.settings.sglang_model,
            "messages": [message.model_dump() for message in request.messages],
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "stream": False,
            "stop": [OFFLOAD_TOKEN],
            "no_stop_trim": True,
            "skip_special_tokens": False,
        }
        return await self._post_chat(self.settings.sglang_base_url, body)

    async def _call_glm(
        self,
        messages: list[ChatMessage],
        partial: str,
        max_tokens: int,
    ) -> dict[str, Any]:
        settings = self.settings
        if not settings.glm_base_url or not settings.glm_model:
            raise UpstreamError(
                "SLM requested offload, but GLM_BASE_URL and GLM_MODEL are not configured"
            )

        relay_messages = [
            {"role": "system", "content": HANDOFF_SYSTEM_PROMPT},
            *[message.model_dump() for message in messages],
            {
                "role": "assistant",
                "content": f"<part_think>{_strip_think_tags(partial)}</part_think>",
            },
        ]
        body = {
            "model": settings.glm_model,
            "messages": relay_messages,
            "max_tokens": max_tokens,
            "stream": False,
        }
        headers = (
            {"Authorization": f"Bearer {settings.glm_api_key}"}
            if settings.glm_api_key
            else None
        )
        return await self._post_chat(settings.glm_base_url, body, headers=headers)

    async def _post_chat(
        self,
        base_url: str,
        body: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{base_url.rstrip('/')}/chat/completions"
        try:
            response = await self.client.post(url, json=body, headers=headers)
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise UpstreamError(f"upstream request failed: {exc}") from exc

        if not data.get("choices"):
            raise UpstreamError("upstream returned no choices")
        return data


def _message_parts(data: dict[str, Any]) -> tuple[str, str]:
    message = data["choices"][0].get("message") or {}
    reasoning = str(message.get("reasoning_content") or message.get("reasoning") or "")
    content = str(message.get("content") or "")
    return reasoning, content


def _render_message(reasoning: str, content: str) -> str:
    reasoning = _strip_think_tags(reasoning)
    return f"<think>{reasoning}</think>{content}" if reasoning else content


def _finish_reason(data: dict[str, Any]) -> str:
    return str(data["choices"][0].get("finish_reason") or "stop")


def _usage(raw: Any) -> TokenUsage:
    raw = raw if isinstance(raw, dict) else {}
    prompt_tokens = int(raw.get("prompt_tokens") or 0)
    completion_tokens = int(raw.get("completion_tokens") or 0)
    return TokenUsage(
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=int(raw.get("total_tokens") or prompt_tokens + completion_tokens),
    )


def _strip_think_tags(text: str) -> str:
    return text.replace("<think>", "").replace("</think>", "")
