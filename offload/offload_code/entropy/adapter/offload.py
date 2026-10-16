"""Tool-call helpers. Requests keep the caller's own system prompt."""

from __future__ import annotations

import json
import secrets
from typing import Any


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


def _arguments_as_openai_json(arguments: Any) -> str:
    if isinstance(arguments, str):
        return arguments
    try:
        return json.dumps(arguments if arguments is not None else {}, ensure_ascii=False)
    except TypeError:
        return json.dumps({"_raw": str(arguments)}, ensure_ascii=False)



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

