"""Self-contained SLM (+ optional LLM offload) adapter with online stats.

Primary path for mini-extra: OpenAI ``/v1/chat/completions`` (keeps
``reasoning_content`` across turns). Anthropic ``/v1/messages`` remains for
back-compat.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from aiohttp import web

from . import offload as ol
from .openai_api import EndpointConfig, call_openai_chat
from .protocol import (
    flatten_translated_to_openai,
    fold_mid_list_system_into_user,
    normalize_openai_request_messages,
    openai_reply_from_parts,
    parse_context_length_error,
    reply_from_parts,
    respond,
    respond_openai,
    router_usage,
    tools_to_chat_tools,
    translate_messages,
)
from .stats import StatsStore, TurnStats, require_usage_tokens

logger = logging.getLogger(__name__)

_INSTANCE_ID_RE = re.compile(
    r"\b([a-zA-Z0-9_.-]+__[a-zA-Z0-9_.-]+-\d+)\b"
)


@dataclass
class Session:
    sampling_defaults: dict = field(default_factory=dict)
    max_context_tokens: int = 128000
    sample_error: str | None = None
    instance_hint: str = ""
    task_label: str = ""


def _stable_instance_sid(body: dict, base: str) -> str:
    parts: list[str] = [base]
    system = body.get("system")
    if system is not None:
        parts.append(str(system)[:2000])
    messages = body.get("messages")
    if isinstance(messages, list):
        for msg in messages[:3]:
            if not isinstance(msg, dict):
                continue
            role = msg.get("role")
            if role not in ("system", "user"):
                continue
            parts.append(f"{role}:{str(msg.get('content') or '')[:2000]}")
            if role == "user":
                break
    digest = hashlib.sha1("\n".join(parts).encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"{base}-{digest}"


def _request_base_sid(request: web.Request) -> str:
    auth = (request.headers.get("Authorization") or "").strip()
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        if token:
            return token
    key = (request.headers.get("X-Api-Key") or "").strip()
    return key or "mini-extra"


def _task_label(body: dict) -> str:
    hint = _guess_instance_hint(body)
    if hint:
        return hint
    messages = body.get("messages")
    if not isinstance(messages, list):
        return ""
    for msg in messages:
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        text = msg.get("content")
        if not isinstance(text, str):
            text = str(text or "")
        text = " ".join(text.split())
        prefix = "please solve this issue:"
        if text.lower().startswith(prefix):
            text = text[len(prefix) :].strip()
        return text[:100]
    return ""


def _guess_instance_hint(body: dict) -> str:
    blobs: list[str] = []
    system = body.get("system")
    if system is not None:
        blobs.append(str(system)[:4000])
    messages = body.get("messages")
    if isinstance(messages, list):
        for msg in messages[:4]:
            if isinstance(msg, dict):
                blobs.append(str(msg.get("content") or "")[:4000])
    text = "\n".join(blobs)
    m = _INSTANCE_ID_RE.search(text)
    return m.group(1) if m else ""


def generation_max_tokens(sampling_defaults: dict | None = None) -> int | None:
    """Shared per-turn completion budget for SLM + LLM.

    ``None`` / ``0`` = no shared cap (each model may use remaining context).
    Positive N: SLM is capped at N; LLM gets ``max(0, N - slm_completion)``.
    """
    raw = (sampling_defaults or {}).get("max_new_tokens")
    if raw is None:
        return 8192
    n = int(raw)
    return n if n > 0 else None


def llm_max_tokens_from_budget(turn_budget: int | None, slm_completion: int) -> int | None:
    """Remaining shared-budget tokens for the LLM after the SLM turn."""
    if turn_budget is None:
        return None
    return max(0, int(turn_budget) - int(slm_completion))


@dataclass
class _GenResult:
    content: str
    think: str
    tool_calls: list[dict[str, Any]]
    prompt_tokens: int
    completion_tokens: int
    llm_prompt_tokens: int = 0
    llm_completion_tokens: int = 0
    report_split: bool = False
    overflow: str | None = None
    abort_without_llm: bool = False


def _router_response_usage(result: _GenResult) -> dict[str, int] | None:
    if not result.report_split:
        return None
    return router_usage(
        result.prompt_tokens,
        result.completion_tokens,
        result.llm_prompt_tokens,
        result.llm_completion_tokens,
    )


class OffloadAdapter:
    """OpenAI / Anthropic → SLM API → optional LLM offload; stats online."""

    def __init__(
        self,
        *,
        slm: EndpointConfig,
        llm: EndpointConfig,
        use_llm: bool = True,
        slm_enable_thinking: bool = True,
        slm_reasoning_effort: str | None = None,
        stop_on_offload_close: bool = True,
        slm_stop_token_ids: list[int] | None = None,
        slm_skip_special_tokens: bool | None = None,
        sampling_defaults: dict | None = None,
        slm_sampling: dict | None = None,
        llm_sampling: dict | None = None,
        max_context_tokens: int = 128000,
        stats_dir: str | None = None,
        max_turns_per_session: int = 0,
        offload_mode: str = "handoff",
    ) -> None:
        self.slm = slm
        self.llm = llm
        self.use_llm = bool(use_llm)
        self.slm_enable_thinking = slm_enable_thinking
        self.slm_reasoning_effort = slm_reasoning_effort
        self.stop_on_offload_close = stop_on_offload_close
        self.slm_stop_token_ids = list(slm_stop_token_ids) if slm_stop_token_ids else None
        self.slm_skip_special_tokens = slm_skip_special_tokens
        self._sampling_defaults = dict(sampling_defaults or {})
        self._slm_sampling = dict(slm_sampling or {})
        self._llm_sampling = dict(llm_sampling or {})
        self._max_context_tokens = int(max_context_tokens)
        self.max_turns_per_session = int(max_turns_per_session)
        mode = (offload_mode or "handoff").strip().lower()
        if mode not in ("handoff", "rewrite", "keep"):
            raise ValueError(f"offload_mode must be handoff, rewrite, or keep, got {offload_mode!r}")
        self.offload_mode = mode

        self.store: dict[str, Session] = {}
        self.closed: set[str] = set()
        self.inflight: dict[str, set] = {}
        self.stats = StatsStore(stats_dir)

        self.app = web.Application()
        self.app.router.add_post("/v1/chat/completions", self._run_turn_openai)
        self.app.router.add_post("/v1/messages", self._run_turn)
        self.app.router.add_post("/v1/messages/count_tokens", self._count_tokens)
        self.app.router.add_get("/health", self._health)
        self.app.router.add_get("/stats", self._stats_get)

    async def _health(self, _: web.Request) -> web.Response:
        return web.Response(text="ok")

    async def _stats_get(self, _: web.Request) -> web.Response:
        return web.json_response(self.stats.summary())

    async def _count_tokens(self, request: web.Request) -> web.Response:
        await request.read()
        return web.json_response({"input_tokens": 0})

    def _session_id(self, request: web.Request, body: dict) -> str:
        base = _request_base_sid(request)
        sid = _stable_instance_sid(body if isinstance(body, dict) else {}, base)
        s = self.store.setdefault(sid, Session())
        if not s.sampling_defaults:
            s.sampling_defaults = dict(self._sampling_defaults)
        if not s.max_context_tokens:
            s.max_context_tokens = self._max_context_tokens
        hint = _guess_instance_hint(body)
        if hint and not s.instance_hint:
            s.instance_hint = hint
        label = _task_label(body if isinstance(body, dict) else {})
        if label and not s.task_label:
            s.task_label = label
        return sid

    def _record_turn_stats(
        self,
        *,
        sid: str,
        session: Session,
        turn_idx: int,
        t0: float,
        offloaded: bool,
        offload_outside_think: bool,
        slm_usage: dict[str, Any] | None,
        llm_usage: dict[str, Any] | None,
        last_offload_n: int | None,
        error: str | None = None,
        require_slm_usage: bool = True,
    ) -> None:
        slm_p = slm_c = llm_p = llm_c = 0
        if require_slm_usage and not error:
            slm_p, slm_c = require_usage_tokens(slm_usage, where=f"SLM sid={sid}")
        elif slm_usage:
            try:
                slm_p, slm_c = require_usage_tokens(slm_usage, where=f"SLM sid={sid}")
            except RuntimeError:
                pass
        if llm_usage:
            llm_p, llm_c = require_usage_tokens(llm_usage, where=f"LLM sid={sid}")
        turn = TurnStats(
            turn=turn_idx,
            offloaded=offloaded,
            offload_outside_think=offload_outside_think,
            slm_prompt_tokens=slm_p,
            slm_completion_tokens=slm_c,
            llm_prompt_tokens=llm_p,
            llm_completion_tokens=llm_c,
            elapsed_sec=round(time.monotonic() - t0, 3),
            error=error,
            slm_usage=slm_usage if isinstance(slm_usage, dict) else None,
            llm_usage=llm_usage if isinstance(llm_usage, dict) else None,
        )
        self.stats.record_and_persist(
            sid,
            turn,
            instance_hint=session.instance_hint,
            task=session.task_label or session.instance_hint,
            last_offload_n=last_offload_n,
        )

    async def _generate_with_offload(
        self,
        *,
        sid: str,
        session: Session,
        turn_idx: int,
        t0: float,
        openai_messages: list[dict[str, Any]],
        tools_schema: list[dict] | None,
        offload_history: list[dict[str, Any]],
    ) -> _GenResult:
        """SLM (+ optional LLM offload). ``offload_history`` feeds build_offload_messages."""
        max_tokens = generation_max_tokens(session.sampling_defaults)
        stop_token_ids = self.slm_stop_token_ids
        stop = None if stop_token_ids else ([ol.OFFLOAD_CLOSE] if self.stop_on_offload_close else None)

        slm_content, slm_think, slm_usage, slm_tool_calls = await call_openai_chat(
            self.slm,
            openai_messages,
            max_tokens=max_tokens,
            tools=tools_schema,
            stop=stop,
            stop_token_ids=stop_token_ids,
            skip_special_tokens=self.slm_skip_special_tokens,
            sampling=self._slm_sampling or None,
            enable_thinking=self.slm_enable_thinking,
            reasoning_effort=self.slm_reasoning_effort,
        )

        if slm_content.startswith("[Error:"):
            logger.error("sid=%s SLM error: %s", sid, slm_content[:500])
            max_ctx = int(session.max_context_tokens or 128000)
            overflow = parse_context_length_error(
                slm_content, max_tokens=max_tokens, max_context=max_ctx
            )
            if overflow:
                session.sample_error = overflow
                self.closed.add(sid)
                try:
                    self._record_turn_stats(
                        sid=sid,
                        session=session,
                        turn_idx=turn_idx,
                        t0=t0,
                        offloaded=False,
                        offload_outside_think=False,
                        slm_usage=slm_usage,
                        llm_usage=None,
                        last_offload_n=None,
                        error=overflow,
                        require_slm_usage=False,
                    )
                except Exception:
                    logger.exception("stats record failed on overflow")
                return _GenResult(
                    content=overflow,
                    think="",
                    tool_calls=[],
                    prompt_tokens=0,
                    completion_tokens=0,
                    overflow=overflow,
                )

        raw_output = ol.raw_output_from_slm(slm_content, slm_think)
        content, think, tool_calls = slm_content, (slm_think or raw_output), list(slm_tool_calls or [])

        try:
            slm_prompt_tok, slm_out_tok = require_usage_tokens(slm_usage, where=f"SLM sid={sid}")
        except RuntimeError:
            logger.error("sid=%s SLM response missing/incomplete usage: %r", sid, slm_usage)
            raise

        parsed = ol.parse_valid_offload_directive(raw_output)
        offloaded = False
        offload_outside_think = False
        llm_usage: dict[str, Any] | None = None
        llm_prompt_tok = 0
        llm_completion_tok = 0
        last_offload_n: int | None = None
        abort_without_llm = False
        llm_text: str | None = None
        llm_think_text: str | None = None

        if parsed is not None:
            n, _prefix = parsed
            enable_thinking, reasoning_effort = ol.reasoning_from_n(n)
            last_offload_n = n

            if not self.use_llm:
                # SLM-only: strip residual offload markers and continue (do not abort).
                offloaded = False
                last_offload_n = n
                content = ol._strip_offload_tag_from_text(slm_content or "")
                think = ol._strip_offload_tag_from_text(slm_think or raw_output or "")
                tool_calls = list(slm_tool_calls or [])
                logger.info(
                    "sid=%s offload ignored (use_llm=false) N=%d → continue SLM-only (%.1fs)",
                    sid,
                    n,
                    time.monotonic() - t0,
                )
            else:
                if self.offload_mode == "rewrite":
                    messages = openai_messages
                    llm_max = max_tokens
                    llm_enable_thinking = None
                elif self.offload_mode == "keep":
                    messages = ol.build_offload_messages(
                        offload_history,
                        raw_output,
                        handoff_prompt=False,
                        part_think=False,
                    )
                    llm_max = llm_max_tokens_from_budget(max_tokens, slm_out_tok)
                    llm_enable_thinking = None
                else:
                    messages = ol.build_offload_messages(offload_history, raw_output)
                    llm_max = llm_max_tokens_from_budget(max_tokens, slm_out_tok)
                    llm_enable_thinking = enable_thinking
                llm_content, llm_think, llm_usage, llm_tool_calls = await call_openai_chat(
                    self.llm,
                    messages,
                    max_tokens=llm_max,
                    tools=tools_schema,
                    sampling=self._llm_sampling or None,
                    enable_thinking=llm_enable_thinking,
                    reasoning_effort=reasoning_effort,
                )
                llm_text = llm_content or ""
                llm_think_text = llm_think or ""
                if llm_content.startswith("[Error:"):
                    logger.error("sid=%s LLM error: %s", sid, llm_content[:500])
                if llm_usage is not None:
                    try:
                        llm_prompt_tok, llm_completion_tok = require_usage_tokens(llm_usage, where=f"LLM sid={sid}")
                    except RuntimeError:
                        logger.error("sid=%s LLM response missing/incomplete usage: %r", sid, llm_usage)
                        raise
                elif not llm_content.startswith("[Error:"):
                    logger.error("sid=%s LLM response missing/incomplete usage: %r", sid, llm_usage)
                    raise RuntimeError(f"LLM sid={sid} missing usage")
                if self.offload_mode == "handoff" and not enable_thinking:
                    llm_think = ""
                offloaded = True
                if self.offload_mode == "rewrite":
                    content = llm_content or ""
                    think = llm_think or ""
                    tool_calls = list(llm_tool_calls or [])
                else:
                    wire, _finish = ol.amend_reply_openai(
                        raw_output=raw_output,
                        llm_content=llm_content,
                        llm_think=llm_think,
                        llm_tool_calls=llm_tool_calls,
                        slm_tool_calls=slm_tool_calls,
                    )
                    content = wire.get("content") or ""
                    think = str(wire.get("reasoning_content") or "")
                    tool_calls = list(wire.get("tool_calls") or [])
                logger.info(
                    "sid=%s offload mode=%s N=%d effort=%s slm_p=%d slm_c=%d llm_max=%s (%.1fs)",
                    sid,
                    self.offload_mode,
                    n,
                    reasoning_effort,
                    slm_prompt_tok,
                    slm_out_tok,
                    llm_max if llm_max is not None else "remaining",
                    time.monotonic() - t0,
                )
        else:
            if ol.parse_offload_directive(raw_output) is not None:
                offload_outside_think = True
                logger.info("sid=%s skip LLM: offload span outside <think>", sid)

        self.stats.append_turn_trace(
            {
                "time": round(time.time(), 3),
                "sid": sid,
                "task": session.task_label or session.instance_hint or sid,
                "turn": turn_idx,
                "offload_mode": self.offload_mode,
                "offloaded": bool(offloaded),
                "offload_n": last_offload_n,
                "slm_thinking": slm_think or "",
                "slm_output": slm_content or "",
                "slm_raw": raw_output,
                "llm_thinking": llm_think_text,
                "llm_output": llm_text,
            }
        )
        self._record_turn_stats(
            sid=sid,
            session=session,
            turn_idx=turn_idx,
            t0=t0,
            offloaded=offloaded,
            offload_outside_think=offload_outside_think,
            slm_usage=slm_usage,
            llm_usage=llm_usage,
            last_offload_n=last_offload_n,
            error=None,
            require_slm_usage=True,
        )
        if abort_without_llm:
            self.closed.add(sid)
        return _GenResult(
            content=content if content is not None else "",
            think=think,
            tool_calls=tool_calls,
            prompt_tokens=slm_prompt_tok,
            completion_tokens=slm_out_tok,
            llm_prompt_tokens=llm_prompt_tok,
            llm_completion_tokens=llm_completion_tok,
            report_split=True,
            abort_without_llm=abort_without_llm,
        )

    def _begin_turn(
        self, request: web.Request, body: dict
    ) -> tuple[str, Session, int] | tuple[str, str] | web.Response:
        """Return (sid, session, turn_idx), or (sid, closed_reason), or an error Response."""
        sid = self._session_id(request, body)
        if sid in self.closed:
            s = self.store.get(sid)
            reason = s.sample_error if s is not None else None
            if reason:
                return sid, str(reason)
            return web.Response(status=503, text="session closed")
        s = self.store.setdefault(sid, Session())
        sess_stats = self.stats.get_or_create(sid, instance_hint=s.instance_hint)
        if self.max_turns_per_session > 0 and sess_stats.turns >= self.max_turns_per_session:
            return web.Response(status=503, text="turn cap exceeded")
        return sid, s, sess_stats.turns

    async def _run_turn_openai(self, request: web.Request) -> web.StreamResponse:
        """OpenAI Chat Completions — preserves reasoning_content across turns."""
        body = await request.json()
        fold_mid_list_system_into_user(body)
        # Only teach the model about offload when LLM handoff is enabled.
        if self.use_llm and self.offload_mode == "handoff":
            ol.inject_offload_into_request_body(body)

        begun = self._begin_turn(request, body)
        if isinstance(begun, web.Response):
            return begun
        if len(begun) == 2:
            _sid, closed_reason = begun  # type: ignore[misc]
            wire, finish = openai_reply_from_parts(content=str(closed_reason), think="", tool_calls=[])
            return await respond_openai(request, body, wire, finish, 0, 0)
        sid, s, turn_idx = begun  # type: ignore[misc]

        task = asyncio.current_task()
        self.inflight.setdefault(sid, set()).add(task)
        t0 = time.monotonic()
        try:
            history = normalize_openai_request_messages(body.get("messages") or [])
            tools_schema = body.get("tools") if isinstance(body.get("tools"), list) else None
            result = await self._generate_with_offload(
                sid=sid,
                session=s,
                turn_idx=turn_idx,
                t0=t0,
                openai_messages=history,
                tools_schema=tools_schema,
                offload_history=history,
            )
            wire, finish = openai_reply_from_parts(
                content=result.content,
                think=result.think,
                tool_calls=result.tool_calls,
            )
            return await respond_openai(
                request,
                body,
                wire,
                finish,
                result.prompt_tokens,
                result.completion_tokens,
                usage=_router_response_usage(result),
            )
        except (ConnectionResetError, asyncio.CancelledError) as e:
            logger.warning(
                "sid=%s client disconnected: %s after %.1fs",
                sid,
                type(e).__name__,
                time.monotonic() - t0,
            )
            if isinstance(e, asyncio.CancelledError):
                raise
            return web.Response(status=499, text="client disconnected")
        finally:
            self.inflight.get(sid, set()).discard(task)

    async def _run_turn(self, request: web.Request) -> web.StreamResponse:
        """Anthropic Messages (back-compat). Prefer /v1/chat/completions for eval."""
        body = await request.json()
        fold_mid_list_system_into_user(body)
        if self.use_llm and self.offload_mode == "handoff":
            ol.inject_offload_into_request_body(body)

        begun = self._begin_turn(request, body)
        if isinstance(begun, web.Response):
            return begun
        if len(begun) == 2:
            _sid, closed_reason = begun  # type: ignore[misc]
            blocks, stop_reason, _ = reply_from_parts(content=str(closed_reason), think="", tool_calls=[])
            return await respond(request, body, blocks, stop_reason, 0, 0)
        sid, s, turn_idx = begun  # type: ignore[misc]

        task = asyncio.current_task()
        self.inflight.setdefault(sid, set()).add(task)
        t0 = time.monotonic()
        try:
            translated = translate_messages(body.get("messages") or [], body.get("system"))
            tools_schema = tools_to_chat_tools(body.get("tools"))
            openai_messages = flatten_translated_to_openai(translated)
            result = await self._generate_with_offload(
                sid=sid,
                session=s,
                turn_idx=turn_idx,
                t0=t0,
                openai_messages=openai_messages,
                tools_schema=tools_schema,
                offload_history=translated,
            )
            blocks, stop_reason, _ = reply_from_parts(
                content=result.content,
                think=result.think,
                tool_calls=result.tool_calls,
            )
            return await respond(
                request, body, blocks, stop_reason, result.prompt_tokens, result.completion_tokens
            )
        except (ConnectionResetError, asyncio.CancelledError) as e:
            logger.warning(
                "sid=%s client disconnected: %s after %.1fs",
                sid,
                type(e).__name__,
                time.monotonic() - t0,
            )
            if isinstance(e, asyncio.CancelledError):
                raise
            return web.Response(status=499, text="client disconnected")
        finally:
            self.inflight.get(sid, set()).discard(task)
