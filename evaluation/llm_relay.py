"""GLM offload relay helpers for evaluation.

DashScope / offload-continuation path used by ``benchmark_relay.py``.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import requests
from tqdm import tqdm

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


def _offload_prefix(raw: str) -> str:
    """Text before ``OFFLOAD_TAG`` (tag and redirect markers removed)."""
    offload_idx = raw.find(OFFLOAD_TAG)
    prefix = raw[:offload_idx] if offload_idx >= 0 else raw
    return prefix.replace(OFFLOAD_TAG, "").replace(REDIRECT_END, "")


def _extract_user_content(prompt: Any) -> str:
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


def _completion_token_count(completion_ids: list[Any] | None, idx: int) -> int:
    """Number of tokens the small model generated for sample ``idx``."""
    if not completion_ids or idx >= len(completion_ids):
        return 0
    ids = completion_ids[idx]
    if isinstance(ids, list):
        return len(ids)
    return int(ids)


def _glm_max_tokens(total_budget: int, completion_ids: list[Any] | None, idx: int) -> int:
    """GLM ``max_tokens`` = frontend total budget minus small-model completion length."""
    return max(0, total_budget - _completion_token_count(completion_ids, idx))


def _build_offload_messages(prompt: Any, response: str) -> list[dict[str, str]]:
    """Build DashScope chat messages for assistant continuation after offload tag."""
    user_content = _extract_user_content(prompt)
    assistant_partial = _offload_prefix(response).strip()

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


def _call_dashscope_chat(
    messages: list[dict[str, str]],
    *,
    api_key: str,
    base_url: str,
    model: str,
    max_tokens: int,
    timeout: float = 600.0,
    enable_thinking: bool = True,
) -> tuple[str, str, dict[str, Any] | None]:
    if not api_key:
        return "[Error: DASHSCOPE_API_KEY not set]", "", None

    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "chat_template_kwargs": {"enable_thinking": enable_thinking},
    }

    try:
        response = requests.post(url, headers=headers, json=body, timeout=timeout)
        if response.status_code != 200:
            return (
                f"[Error: DashScope status {response.status_code}: {response.text}]",
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
        return f"[Error: DashScope call failed: {exc}]", "", None


def _complete_offload_response(
    response: str,
    prompt: Any,
    *,
    api_key: str,
    base_url: str,
    model: str,
    max_tokens: int,
    sample_idx: int | None = None,
    enable_thinking: bool = True,
) -> tuple[str, dict[str, Any] | None]:
    del sample_idx  # kept for API parity with phase2/reward.py
    if OFFLOAD_TAG not in response or max_tokens <= 0:
        return response, None

    messages = _build_offload_messages(prompt, response)
    generated, think, usage = _call_dashscope_chat(
        messages,
        api_key=api_key,
        base_url=base_url,
        model=model,
        max_tokens=max_tokens,
        enable_thinking=enable_thinking,
    )

    prefix = _offload_prefix(response)
    res = (
        "<think>"
        + prefix.replace("<think>", "").replace("</think>", "")
        + think
        + "</think>"
        + generated
    )
    return res, usage


def complete_offload_batch(
    responses: list[str],
    prompts: list[Any],
    *,
    api_key: str,
    base_url: str,
    model: str,
    max_tokens: int,
    max_workers: int,
    completion_ids: list[Any] | None = None,
    enable_thinking: bool = True,
) -> tuple[list[str], list[dict[str, Any] | None]]:
    """Relay samples that contain ``OFFLOAD_TAG`` via GLM; others pass through."""
    indices = [i for i, resp in enumerate(responses) if OFFLOAD_TAG in resp]
    completed = list(responses)
    usages: list[dict[str, Any] | None] = [None] * len(responses)
    if not indices:
        return completed, usages

    workers = max(1, min(max_workers, len(indices)))
    total = len(indices)

    def _run(idx: int) -> tuple[int, str, dict[str, Any] | None]:
        glm_max_tokens = _glm_max_tokens(max_tokens, completion_ids, idx)
        full, usage = _complete_offload_response(
            responses[idx],
            prompts[idx],
            api_key=api_key,
            base_url=base_url,
            model=model,
            max_tokens=glm_max_tokens,
            sample_idx=idx,
            enable_thinking=enable_thinking,
        )
        return idx, full, usage

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_run, idx) for idx in indices]
        for future in tqdm(
            as_completed(futures),
            total=total,
            desc="[glm] relay",
            unit="sample",
        ):
            idx, full, usage = future.result()
            completed[idx] = full
            usages[idx] = usage
    return completed, usages


# Alias matching phase2/reward.py name for drop-in imports.
_complete_offload_batch = complete_offload_batch
