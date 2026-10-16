"""GLM / DashScope offload relay for math (bare ``<|llm_offload|>``)."""

from __future__ import annotations

from typing import Any

import requests

OFFLOAD_TAG = "<|llm_offload|>"
REDIRECT_END = "<|im_end|>"

DEFAULT_REMOTE_HANDOFF_PROMPT = (
    "You are a helpful assistant completing a task that was partially solved "
    "by a smaller local model before offload.\n"
    "Collaborative handoff protocol:\n"
    "- The assistant message may contain <part_think>...</part_think> with reasoning "
    "the small model already produced before offload.\n"
    "- Because part of the reasoning is already in <part_think>, continue from "
    "where it stopped: your reasoning channel should pick up at the first "
    "unresolved step and carry forward to the final answer. Do not repeat, "
    "paraphrase, or re-derive anything already present in <part_think>.\n"
    "- If <part_think> already concludes the task, proceed directly to the final answer.\n"
    "- Put the user-facing answer only in normal assistant content. Never quote "
    "or mention <part_think> to the user.\n"
    "- <part_think> is an internal marker, not user input."
)


def offload_prefix(raw: str) -> str:
    """Text before ``OFFLOAD_TAG`` (tag and redirect markers removed)."""
    offload_idx = raw.find(OFFLOAD_TAG)
    prefix = raw[:offload_idx] if offload_idx >= 0 else raw
    return prefix.replace(OFFLOAD_TAG, "").replace(REDIRECT_END, "")


def extract_user_content(prompt: Any) -> str:
    if isinstance(prompt, list):
        parts: list[str] = []
        for msg in prompt:
            if not isinstance(msg, dict) or msg.get("role") != "user":
                continue
            content = msg.get("content", "")
            if isinstance(content, list):
                texts = [
                    str(part.get("text", ""))
                    for part in content
                    if isinstance(part, dict) and part.get("type") == "text"
                ]
                parts.append("\n".join(texts))
            else:
                parts.append(str(content))
        return "\n".join(parts).strip()
    return str(prompt).strip()


def build_offload_messages(prompt: Any, response: str) -> list[dict[str, str]]:
    """Build chat messages for assistant continuation after offload tag."""
    user_content = extract_user_content(prompt)
    assistant_partial = offload_prefix(response).strip()

    messages: list[dict[str, str]] = [
        {"role": "system", "content": DEFAULT_REMOTE_HANDOFF_PROMPT},
        {"role": "user", "content": user_content},
    ]
    if assistant_partial:
        messages.append(
            {
                "role": "assistant",
                "content": (
                    "<part_think>"
                    + assistant_partial.replace("<think>", "").replace("</think>", "")
                    + "</part_think>"
                ),
            }
        )
    return messages


def call_llm_chat(
    messages: list[dict[str, str]],
    *,
    api_key: str,
    base_url: str,
    model: str,
    max_tokens: int,
    timeout: float = 600.0,
    enable_thinking: bool = True,
    temperature: float = 1.0,
    top_p: float = 1.0,
) -> tuple[str, str, dict[str, Any] | None]:
    if not api_key:
        return "[Error: LLM API key not set]", "", None

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }

    try:
        response = requests.post(url, headers=headers, json=body, timeout=timeout)
        if response.status_code != 200:
            return (
                f"[Error: LLM status {response.status_code}: {response.text}]",
                "",
                None,
            )
        data = response.json()
        message = data["choices"][0].get("message", {})
        think = str(message.get("reasoning") or message.get("reasoning_content") or "")
        content = str(message.get("content") or "")
        usage = data.get("usage")
        if usage is not None and not isinstance(usage, dict):
            usage = None
        return content, think, usage
    except Exception as exc:
        return f"[Error: LLM call failed: {exc}]", "", None


def complete_offload_response(
    response: str,
    prompt: Any,
    *,
    api_key: str,
    base_url: str,
    model: str,
    max_tokens: int,
    enable_thinking: bool = True,
    temperature: float = 1.0,
    top_p: float = 1.0,
) -> tuple[str, dict[str, Any] | None]:
    if OFFLOAD_TAG not in response or max_tokens <= 0:
        return response, None

    messages = build_offload_messages(prompt, response)
    generated, think, usage = call_llm_chat(
        messages,
        api_key=api_key,
        base_url=base_url,
        model=model,
        max_tokens=max_tokens,
        enable_thinking=enable_thinking,
        temperature=temperature,
        top_p=top_p,
    )

    prefix = offload_prefix(response)
    res = (
        "<think>"
        + prefix.replace("<think>", "").replace("</think>", "")
        + think
        + "</think>"
        + generated
    )
    return res, usage
