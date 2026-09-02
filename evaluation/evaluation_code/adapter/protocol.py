"""Anthropic Messages wire: translate request, build/stream response."""

from __future__ import annotations

import json
import re
import secrets
from typing import Any

from aiohttp import web

from .offload import flatten_content, openai_tool_calls_to_anthropic_blocks, tool_call_dict

_CTX_WINDOW_RE = re.compile(r"maximum context length is (\d+)", re.I)
_CTX_OUTPUT_RE = re.compile(r"requested (\d+) output tokens", re.I)
_CTX_INPUT_RE = re.compile(r"prompt contains at least (\d+) input tokens", re.I)
_CTX_HINTS = (
    "maximum context length",
    "context_length_exceeded",
    "context length",
    "input_tokens",
)
_MID_SYSTEM_WRAP_PREFIX = "<system-reminder>\n"
_MID_SYSTEM_WRAP_SUFFIX = "\n</system-reminder>\n"


def parse_context_length_error(
    slm_content: str, *, max_tokens: int | None = None, max_context: int
) -> str | None:
    text = slm_content or ""
    if not text.startswith("[Error:"):
        return None
    low = text.lower()
    if not any(h in low for h in _CTX_HINTS):
        return None
    window = max_context
    m = _CTX_WINDOW_RE.search(text)
    if m:
        window = int(m.group(1))
    out_tok = max_tokens
    m = _CTX_OUTPUT_RE.search(text)
    if m:
        out_tok = int(m.group(1))
    in_tok = None
    m = _CTX_INPUT_RE.search(text)
    if m:
        in_tok = int(m.group(1))
    out_label = "remaining" if out_tok is None else str(out_tok)
    if in_tok is not None:
        total = f"{in_tok}+{out_label}" if out_tok is None else str(in_tok + out_tok)
        return (
            f"context_length_exceeded: SLM context window is {window} tokens; "
            f"this request needs prompt>={in_tok} + max_tokens={out_label} = {total}, "
            f"which exceeds {window}. Sample marked failed."
        )
    return (
        f"context_length_exceeded: SLM context window is {window} tokens; "
        f"prompt + max_tokens={out_label} exceeded the limit. Sample marked failed."
    )


def fold_mid_list_system_into_user(body_obj: dict) -> bool:
    msgs = body_obj.get("messages")
    if not isinstance(msgs, list) or not msgs:
        return False
    system_idx = [i for i, m in enumerate(msgs) if isinstance(m, dict) and m.get("role") == "system" and i > 0]
    if not system_idx:
        return False

    def _promote_to_list(msg: dict) -> list:
        c = msg.get("content")
        if isinstance(c, list):
            return c
        msg["content"] = [{"type": "text", "text": c if isinstance(c, str) else ""}]
        return msg["content"]

    def _wrap(text: str) -> dict:
        return {"type": "text", "text": _MID_SYSTEM_WRAP_PREFIX + text + _MID_SYSTEM_WRAP_SUFFIX}

    changed = False
    TOMBSTONE: dict = {"__folded__": True}
    for i in system_idx:
        sys_msg = msgs[i]
        wrapped = _wrap(flatten_content(sys_msg.get("content")))
        target = None
        for j in range(i - 1, -1, -1):
            cand = msgs[j]
            if isinstance(cand, dict) and cand.get("role") == "user":
                target = cand
                _promote_to_list(target).append(wrapped)
                break
        if target is None:
            for j in range(i + 1, len(msgs)):
                cand = msgs[j]
                if isinstance(cand, dict) and cand.get("role") == "user":
                    target = cand
                    _promote_to_list(target).insert(0, wrapped)
                    break
        if target is None:
            msgs[i] = {"role": "user", "content": [wrapped]}
            changed = True
            continue
        msgs[i] = TOMBSTONE
        changed = True
    if changed:
        body_obj["messages"] = [m for m in msgs if m is not TOMBSTONE]
    return changed


def translate_messages(msgs: list[dict], system: Any) -> list[dict]:
    translated: list[dict] = []
    if system:
        translated.append({"role": "system", "content": flatten_content(system)})
    for m in msgs:
        if not isinstance(m, dict):
            continue
        role, content = m.get("role"), m.get("content")
        if role == "user":
            blocks = content if isinstance(content, list) else [{"type": "text", "text": flatten_content(content)}]
            for b in blocks:
                if isinstance(b, dict) and b.get("type") == "tool_result":
                    tool_msg: dict[str, Any] = {
                        "role": "tool",
                        "content": flatten_content(b.get("content")),
                    }
                    tool_use_id = b.get("tool_use_id")
                    if tool_use_id:
                        tool_msg["tool_call_id"] = tool_use_id
                    translated.append(tool_msg)
                elif isinstance(b, dict) and b.get("type") == "text":
                    translated.append({"role": "user", "content": b.get("text", "")})
                else:
                    translated.append({"role": "user", "content": flatten_content(b)})
        elif role == "assistant":
            texts, thinkings, tcs = [], [], []
            blocks = content if isinstance(content, list) else [{"type": "text", "text": flatten_content(content)}]
            for b in blocks:
                if not isinstance(b, dict):
                    continue
                if b.get("type") == "text":
                    texts.append(b.get("text", ""))
                elif b.get("type") == "thinking":
                    thinkings.append(b.get("thinking", ""))
                elif b.get("type") == "tool_use":
                    tc = tool_call_dict(b.get("name", "tool"), b.get("input"))
                    if b.get("id"):
                        tc = {**tc, "id": b["id"]}
                    tcs.append(tc)
            mo: dict[str, Any] = {"role": "assistant", "content": "".join(texts)}
            if thinkings:
                mo["reasoning_content"] = "".join(thinkings)
            if tcs:
                mo["tool_calls"] = tcs
            translated.append(mo)
        elif role == "system":
            translated.append({"role": "system", "content": flatten_content(content)})
    return translated


def tools_to_chat_tools(anth_tools: list[dict] | None) -> list[dict] | None:
    if not anth_tools:
        return None
    ts: list[dict] = []
    for t in anth_tools:
        if not isinstance(t, dict) or "name" not in t:
            continue
        ts.append(
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("input_schema") or t.get("parameters") or {"type": "object", "properties": {}},
                },
            }
        )
    return ts or None


def flatten_translated_to_openai(translated: list[dict]) -> list[dict[str, Any]]:
    from .offload import _arguments_as_openai_json

    out: list[dict[str, Any]] = []
    for m in translated:
        if not isinstance(m, dict):
            continue
        role = m.get("role")
        if role == "assistant":
            msg: dict[str, Any] = {"role": "assistant", "content": m.get("content") or ""}
            if m.get("reasoning_content"):
                msg["reasoning_content"] = m["reasoning_content"]
            tcs = m.get("tool_calls")
            if isinstance(tcs, list) and tcs:
                openai_tcs = []
                for i, tc in enumerate(tcs):
                    if not isinstance(tc, dict):
                        continue
                    fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                    name = fn.get("name") or tc.get("name")
                    if not name:
                        continue
                    args = fn.get("arguments") if fn else tc.get("arguments")
                    openai_tcs.append(
                        {
                            "id": str(tc.get("id") or f"call_{i}"),
                            "type": "function",
                            "function": {
                                "name": str(name),
                                "arguments": _arguments_as_openai_json(args),
                            },
                        }
                    )
                if openai_tcs:
                    msg["tool_calls"] = openai_tcs
            out.append(msg)
        elif role == "tool":
            out.append(
                {
                    "role": "tool",
                    "tool_call_id": str(m.get("tool_call_id") or "unknown"),
                    "content": m.get("content") or "",
                }
            )
        elif role in ("system", "user"):
            out.append({"role": role, "content": m.get("content") or ""})
    return out


def reply_from_parts(*, content: str, think: str, tool_calls: list[dict[str, Any]]) -> tuple[list[dict], str, dict]:
    blocks: list[dict] = []
    if think:
        blocks.append({"type": "thinking", "thinking": think})
    if content:
        blocks.append({"type": "text", "text": content})
    anth_tools = openai_tool_calls_to_anthropic_blocks(tool_calls)
    blocks.extend(anth_tools)
    if not blocks:
        blocks.append({"type": "text", "text": ""})
    stop_reason = "tool_use" if anth_tools else "end_turn"
    manager_message: dict[str, Any] = {"role": "assistant", "content": content or ""}
    if think:
        manager_message["reasoning_content"] = think
    if anth_tools:
        manager_message["tool_calls"] = [
            tool_call_dict(b["name"], b.get("input")) | ({"id": b["id"]} if b.get("id") else {})
            for b in anth_tools
        ]
    return blocks, stop_reason, manager_message


def render_response(body: dict, blocks: list[dict], stop_reason: str, in_tok: int, out_tok: int) -> dict:
    return {
        "id": f"msg_{secrets.token_hex(12)}",
        "type": "message",
        "role": "assistant",
        "model": body.get("model", "swe-run-offload"),
        "content": blocks,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
    }


async def render_stream(request, blocks, stop_reason, in_tok, out_tok) -> web.StreamResponse:
    out = web.StreamResponse(
        status=200,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
    await out.prepare(request)
    ms_data = {
        "type": "message_start",
        "message": {
            "id": f"msg_{secrets.token_hex(12)}",
            "type": "message",
            "role": "assistant",
            "model": "swe-run-offload",
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": in_tok, "output_tokens": 0},
        },
    }
    await out.write(f"event: message_start\ndata: {json.dumps(ms_data, ensure_ascii=False)}\n\n".encode())
    for idx, block in enumerate(blocks):
        bt = block["type"]
        if bt == "thinking":
            start = {"type": "thinking", "thinking": ""}
            delta = {"type": "thinking_delta", "thinking": block["thinking"]}
        elif bt == "text":
            start = {"type": "text", "text": ""}
            delta = {"type": "text_delta", "text": block["text"]}
        else:
            start = {"type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}
            delta = {
                "type": "input_json_delta",
                "partial_json": json.dumps(block["input"], ensure_ascii=False),
            }
        cbs_data = {"type": "content_block_start", "index": idx, "content_block": start}
        await out.write(f"event: content_block_start\ndata: {json.dumps(cbs_data, ensure_ascii=False)}\n\n".encode())
        cbd_data = {"type": "content_block_delta", "index": idx, "delta": delta}
        await out.write(f"event: content_block_delta\ndata: {json.dumps(cbd_data, ensure_ascii=False)}\n\n".encode())
        cbe_data = {"type": "content_block_stop", "index": idx}
        await out.write(f"event: content_block_stop\ndata: {json.dumps(cbe_data, ensure_ascii=False)}\n\n".encode())
    md_data = {
        "type": "message_delta",
        "delta": {"stop_reason": stop_reason, "stop_sequence": None},
        "usage": {"input_tokens": in_tok, "output_tokens": out_tok},
    }
    await out.write(f"event: message_delta\ndata: {json.dumps(md_data, ensure_ascii=False)}\n\n".encode())
    await out.write(b"event: message_stop\ndata: {\"type\": \"message_stop\"}\n\n")
    return out


async def respond(request, body, blocks, stop_reason, in_tok, out_tok) -> web.StreamResponse:
    stream = body.get("stream") is True or "text/event-stream" in request.headers.get("Accept", "")
    if stream:
        return await render_stream(request, blocks, stop_reason, in_tok, out_tok)
    return web.json_response(render_response(body, blocks, stop_reason, in_tok, out_tok))
