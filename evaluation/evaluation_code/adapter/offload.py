"""Offload directive parsing and GLM handoff message building."""

from __future__ import annotations

import json
import os
import re
import secrets
from typing import Any

OFFLOAD_OPEN = "<|llm_offload|>"
OFFLOAD_CLOSE = "<|/llm_offload|>"
_OFFLOAD_SPAN_RE = re.compile(re.escape(OFFLOAD_OPEN) + r"(\d)" + re.escape(OFFLOAD_CLOSE))
_OFFLOAD_OPEN_DIGIT_RE = re.compile(
    re.escape(OFFLOAD_OPEN) + r"(\d)(?:" + re.escape(OFFLOAD_CLOSE) + r")?$"
)

DEFAULT_OFFLOAD_MAX_TOKENS = int(os.environ.get("OFFLOAD_MAX_TOKENS", "0"))

CODING_HANDOFF_PROMPT = (
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

OFFLOAD_SYSTEM_PROMPT_APPEND = (
    "For very difficult steps, you can output "
    f"{OFFLOAD_OPEN}N{OFFLOAD_CLOSE} where N is 0-9 indicating the thinking "
    "level for a more capable model."
)


def flatten_content(c: Any) -> str:
    if c is None:
        return ""
    if isinstance(c, str):
        return c
    if not isinstance(c, list):
        return str(c)
    parts: list[str] = []
    for b in c:
        if isinstance(b, str):
            parts.append(b)
            continue
        if not isinstance(b, dict):
            parts.append(str(b))
            continue
        t = b.get("type")
        if t in {"text", "input_text", "output_text"}:
            parts.append(b.get("text", ""))
        elif t == "tool_result":
            parts.append(flatten_content(b.get("content")))
        elif t in {"image", "image_url", "input_image"}:
            parts.append("[image omitted]")
        elif "content" in b:
            parts.append(flatten_content(b.get("content")))
        elif "text" in b:
            parts.append(str(b.get("text") or ""))
    return "\n".join(p for p in parts if p)


def tool_call_dict(name: str, arguments: dict | None) -> dict:
    return {"type": "function", "function": {"name": name, "arguments": arguments or {}}}


def offload_system_append_text() -> str:
    return (os.environ.get("SLIME_AGENT_OFFLOAD_SYSTEM_APPEND") or OFFLOAD_SYSTEM_PROMPT_APPEND).strip()


def inject_offload_into_request_body(body: dict) -> None:
    text = offload_system_append_text()
    if not text:
        return
    if "system" in body and body.get("system") is not None:
        body["system"] = _append_to_anthropic_system(body.get("system"), text)
        return
    messages = body.get("messages")
    if isinstance(messages, list):
        _append_to_openai_messages(messages, text)


def _append_to_anthropic_system(system: Any, text: str) -> Any:
    flat = flatten_content(system) if system else ""
    if text in flat:
        return system
    if system is None or system == "":
        return text
    if isinstance(system, str):
        return system.rstrip() + "\n\n" + text
    if isinstance(system, list):
        out = [b for b in system if isinstance(b, dict)]
        out.append({"type": "text", "text": "\n\n" + text})
        return out if out else text
    return flat.rstrip() + "\n\n" + text


def _append_to_openai_messages(messages: list, text: str) -> None:
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("role") != "system":
            continue
        content = msg.get("content")
        flat = content if isinstance(content, str) else flatten_content(content)
        if text in (flat or ""):
            return
        if isinstance(content, str):
            msg["content"] = content.rstrip() + "\n\n" + text
        else:
            msg["content"] = (flat or "").rstrip() + "\n\n" + text
        return
    messages.insert(0, {"role": "system", "content": text})


def parse_offload_directive(raw: str) -> tuple[int, str] | None:
    match = _OFFLOAD_SPAN_RE.search(raw)
    if match is None:
        return None
    return int(match.group(1)), raw[: match.start()]


def offload_span_inside_think(raw: str) -> bool:
    match = _OFFLOAD_SPAN_RE.search(raw)
    if match is None:
        return False
    pos = match.start()
    before = raw[:pos]
    last_open = before.rfind("<think>")
    if last_open >= 0 and "</think>" not in before[last_open:]:
        return True
    first_close = raw.find("</think>")
    if first_close < 0:
        return True
    return pos < first_close


def parse_valid_offload_directive(raw: str) -> tuple[int, str] | None:
    parsed = parse_offload_directive(raw)
    if parsed is None or not offload_span_inside_think(raw):
        return None
    return parsed


def reasoning_from_n(n: int) -> tuple[bool, str | None]:
    if n <= 0:
        return False, None
    if n <= 5:
        return True, "high"
    return True, "max"


def repair_truncated_offload_span(raw: str) -> str:
    if parse_offload_directive(raw) is not None:
        return raw
    m = _OFFLOAD_OPEN_DIGIT_RE.search(raw.rstrip())
    if m is None:
        return raw
    if raw.rstrip().endswith(OFFLOAD_CLOSE):
        return raw
    return raw.rstrip() + OFFLOAD_CLOSE


def raw_output_from_slm(content: str, think: str) -> str:
    content = content or ""
    think = think or ""
    if think and content:
        if "</think>" in think:
            raw = f"{think}\n{content}"
        else:
            raw = f"{think}</think>\n{content}"
    elif think:
        raw = think
    else:
        raw = content
    return repair_truncated_offload_span(raw)


def _strip_offload_tag_from_text(text: str) -> str:
    text = _OFFLOAD_SPAN_RE.sub("", text)
    return text.replace(OFFLOAD_OPEN, "").replace(OFFLOAD_CLOSE, "").rstrip()


def _offload_prefix(raw: str) -> str:
    parsed = parse_offload_directive(raw)
    if parsed is None:
        idx = raw.find(OFFLOAD_OPEN)
        prefix = raw[:idx] if idx >= 0 else raw
    else:
        prefix = parsed[1]
    return _strip_offload_tag_from_text(prefix).strip()


def _arguments_as_openai_json(arguments: Any) -> str:
    if isinstance(arguments, str):
        return arguments
    try:
        return json.dumps(arguments if arguments is not None else {}, ensure_ascii=False)
    except TypeError:
        return json.dumps({"_raw": str(arguments)}, ensure_ascii=False)


def _normalize_openai_tool_calls(tool_calls: list[Any] | None, *, id_prefix: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, call in enumerate(tool_calls or []):
        if not isinstance(call, dict):
            continue
        function = call.get("function") if isinstance(call.get("function"), dict) else {}
        name = function.get("name") or call.get("name") or "tool"
        arguments = function.get("arguments")
        if arguments is None:
            arguments = call.get("arguments", {})
        call_id = call.get("id") or f"{id_prefix}-{i}"
        out.append(
            {
                "id": str(call_id),
                "type": "function",
                "function": {
                    "name": str(name),
                    "arguments": _arguments_as_openai_json(arguments),
                },
            }
        )
    return out


def strip_offload_system_append(text: str) -> str:
    out = text
    for variant in (OFFLOAD_SYSTEM_PROMPT_APPEND, offload_system_append_text()):
        if variant and variant in out:
            out = out.replace(variant, "")
    out = re.sub(r"\n{3,}", "\n\n", out).strip()
    return out


def _assistant_content_for_openai(msg: dict[str, Any]) -> str:
    parts: list[str] = []
    reasoning = msg.get("reasoning_content")
    if isinstance(reasoning, str) and reasoning.strip():
        parts.append(f"<think>\n{reasoning.strip()}\n</think>")
    content = flatten_content(msg.get("content"))
    if content:
        parts.append(content)
    return _strip_offload_tag_from_text("\n\n".join(parts)).strip()


def build_offload_messages(translated: list[dict], raw_output: str) -> list[dict[str, Any]]:
    agent_system_parts: list[str] = []
    rest: list[dict[str, Any]] = []
    pending_tool_ids: list[str] = []
    synth_i = 0

    for msg in translated:
        role = str(msg.get("role") or "user")
        if role == "system":
            text = flatten_content(msg.get("content"))
            cleaned_system = strip_offload_system_append(text) if text else ""
            if cleaned_system:
                agent_system_parts.append(cleaned_system)
            continue
        if role == "user":
            text = _strip_offload_tag_from_text(flatten_content(msg.get("content")))
            if text:
                rest.append({"role": "user", "content": text})
            continue
        if role == "assistant":
            content = _assistant_content_for_openai(msg)
            tool_calls = _normalize_openai_tool_calls(
                msg.get("tool_calls"),
                id_prefix=f"chatcmpl-tool-offload{synth_i}",
            )
            synth_i += 1
            if not content and not tool_calls:
                continue
            out_msg: dict[str, Any] = {"role": "assistant", "content": content or None}
            if tool_calls:
                out_msg["tool_calls"] = tool_calls
                pending_tool_ids = [tc["id"] for tc in tool_calls]
            else:
                pending_tool_ids = []
            rest.append(out_msg)
            continue
        if role == "tool":
            text = _strip_offload_tag_from_text(flatten_content(msg.get("content")))
            tool_call_id = msg.get("tool_call_id") or msg.get("tool_use_id")
            if not tool_call_id and pending_tool_ids:
                tool_call_id = pending_tool_ids.pop(0)
            if not tool_call_id:
                tool_call_id = f"chatcmpl-tool-orphan-{synth_i}"
                synth_i += 1
            rest.append(
                {
                    "role": "tool",
                    "tool_call_id": str(tool_call_id),
                    "content": text if text else "",
                }
            )
            continue
        text = _strip_offload_tag_from_text(flatten_content(msg.get("content")))
        if text:
            rest.append({"role": "user", "content": text})

    system = "\n\n".join([*agent_system_parts, CODING_HANDOFF_PROMPT]).strip()
    messages: list[dict[str, Any]] = [{"role": "system", "content": system}]
    messages.extend(rest)
    partial = _offload_prefix(raw_output)
    cleaned = partial.replace("<think>", "").replace("</think>", "").strip()
    if cleaned:
        messages.append({"role": "assistant", "content": f"<part_think>{cleaned}</part_think>"})
    return messages


def normalize_openai_tools(tools_schema: list[dict] | None) -> list[dict[str, Any]] | None:
    if not tools_schema:
        return None
    out: list[dict[str, Any]] = []
    for tool in tools_schema:
        if not isinstance(tool, dict):
            continue
        function = tool.get("function") if isinstance(tool.get("function"), dict) else None
        if function is not None:
            name = function.get("name")
            if not name:
                continue
            out.append(
                {
                    "type": "function",
                    "function": {
                        "name": name,
                        "description": function.get("description", ""),
                        "parameters": function.get("parameters") or {"type": "object", "properties": {}},
                    },
                }
            )
            continue
        name = tool.get("name")
        if not name:
            continue
        out.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.get("description", ""),
                    "parameters": tool.get("input_schema")
                    or tool.get("parameters")
                    or {"type": "object", "properties": {}},
                },
            }
        )
    return out or None


def parse_openai_tool_calls(raw_tool_calls: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_tool_calls, list):
        return []
    out: list[dict[str, Any]] = []
    for i, call in enumerate(raw_tool_calls):
        if not isinstance(call, dict):
            continue
        function = call.get("function") if isinstance(call.get("function"), dict) else {}
        name = function.get("name") or call.get("name")
        if not name:
            continue
        arguments = function.get("arguments")
        if arguments is None:
            arguments = call.get("arguments", {})
        out.append(
            {
                "id": str(call.get("id") or f"chatcmpl-tool-glm-{i}"),
                "type": "function",
                "function": {
                    "name": str(name),
                    "arguments": _arguments_as_openai_json(arguments),
                },
            }
        )
    return out


def openai_tool_calls_to_anthropic_blocks(tool_calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for tc in tool_calls:
        function = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        args_raw = function.get("arguments")
        if isinstance(args_raw, str):
            try:
                args_obj = json.loads(args_raw)
            except json.JSONDecodeError:
                args_obj = {"_raw": args_raw}
        elif isinstance(args_raw, dict):
            args_obj = args_raw
        else:
            args_obj = {}
        blocks.append(
            {
                "type": "tool_use",
                "id": str(tc.get("id") or f"toolu_{secrets.token_hex(8)}"),
                "name": str(function.get("name") or "tool"),
                "input": args_obj,
            }
        )
    return blocks


def compose_complete_assistant(*, slm_content: str, glm_content: str, glm_think: str) -> tuple[str, str]:
    text = glm_content or ""
    think = "".join(p for p in (slm_content, glm_think) if p)
    return text, think


def amend_reply_wire(
    *,
    raw_output: str,
    glm_content: str,
    glm_think: str,
    glm_tool_calls: list[dict[str, Any]] | None,
    slm_tool_blocks: list[dict[str, Any]] | None = None,
) -> tuple[list[dict], str, dict[str, Any]]:
    """Return (anthropic blocks, stop_reason, manager_message)."""
    text, think = compose_complete_assistant(
        slm_content=raw_output,
        glm_content=glm_content,
        glm_think=glm_think,
    )
    glm_tool_calls = list(glm_tool_calls or [])
    tool_blocks = (
        openai_tool_calls_to_anthropic_blocks(glm_tool_calls)
        if glm_tool_calls
        else list(slm_tool_blocks or [])
    )
    blocks: list[dict] = []
    if think:
        blocks.append({"type": "thinking", "thinking": think})
    if text or not tool_blocks:
        blocks.append({"type": "text", "text": text})
    blocks.extend(tool_blocks)
    if not blocks:
        blocks.append({"type": "text", "text": ""})
    stop_reason = "tool_use" if tool_blocks else "end_turn"

    manager_message: dict[str, Any] = {"role": "assistant", "content": text or ""}
    if think:
        manager_message["reasoning_content"] = think
    if tool_blocks:
        manager_message["tool_calls"] = [
            tool_call_dict(b["name"], b.get("input")) | ({"id": b["id"]} if b.get("id") else {})
            for b in tool_blocks
        ]
    return blocks, stop_reason, manager_message
