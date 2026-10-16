"""SLM adapter that routes a turn to the LLM from thinking entropy.

The small model always generates first. Top-k logprobs inside its thinking
are turned into a per-token entropy and averaged. If that mean is above the
configured threshold, the small model's thinking and answer are dropped and
the large model rewrites the turn. Otherwise the small model's reply is kept.

Primary path: OpenAI ``/v1/chat/completions``. Anthropic ``/v1/messages``
remains for back-compat.
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

from .entropy import mean_think_entropy, should_route
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
    max_context_tokens: int = 0
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
        max_context_tokens: int = 0,
        stats_dir: str | None = None,
        max_turns_per_session: int = 0,
        entropy_threshold: float = 0.5,
        entropy_top_k: int = 20,
        llm_reasoning_effort: str | None = "high",
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
        self.entropy_threshold = float(entropy_threshold)
        self.entropy_top_k = int(entropy_top_k)
        effort = (llm_reasoning_effort or "").strip()
        self.llm_reasoning_effort = effort or None

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
        mean_think_entropy_value: float | None = None,
        think_tokens: int = 0,
        entropy_unavailable: bool = False,
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
            mean_think_entropy=mean_think_entropy_value,
            think_tokens=think_tokens,
            entropy_threshold=self.entropy_threshold,
            entropy_unavailable=entropy_unavailable,
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
    ) -> _GenResult:
        """SLM first; LLM rewrites the turn when mean thinking entropy is too high."""
        max_tokens = generation_max_tokens(session.sampling_defaults)
        stop_token_ids = self.slm_stop_token_ids
        # Do not stop on the offload tag: the whole thinking span is scored.
        stop = None

        slm_content, slm_think, slm_usage, slm_tool_calls, slm_logprobs = await call_openai_chat(
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
            logprobs_top_k=self.entropy_top_k,
        )

        if slm_content.startswith("[Error:"):
            logger.error("sid=%s SLM error: %s", sid, slm_content[:500])
            max_ctx = int(session.max_context_tokens or 0)
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

        content, think, tool_calls = slm_content, slm_think, list(slm_tool_calls or [])

        try:
            slm_prompt_tok, slm_out_tok = require_usage_tokens(slm_usage, where=f"SLM sid={sid}")
        except RuntimeError:
            logger.error("sid=%s SLM response missing/incomplete usage: %r", sid, slm_usage)
            raise

        scored = mean_think_entropy(slm_logprobs, top_k=self.entropy_top_k)
        route = should_route(scored.mean, self.entropy_threshold)
        offloaded = False
        offload_outside_think = False
        llm_usage: dict[str, Any] | None = None
        llm_prompt_tok = 0
        llm_completion_tok = 0
        last_offload_n: int | None = None
        abort_without_llm = False
        llm_text: str | None = None
        llm_think_text: str | None = None
        entropy_text = "na" if scored.mean is None else f"{scored.mean:.4f}"

        if route:
            if not self.use_llm:
                abort_without_llm = True
                offloaded = True
                logger.info(
                    "sid=%s entropy route abort (use_llm=false) mean=%s n=%d threshold=%.4f (%.1fs)",
                    sid,
                    entropy_text,
                    scored.n_tokens,
                    self.entropy_threshold,
                    time.monotonic() - t0,
                )
                content = (
                    "[offload-abort] Thinking entropy exceeded the threshold; "
                    "use_llm=false so the large model was not called and this run stops."
                )
                think = ""
                tool_calls = []
                self.closed.add(sid)
            else:
                # Same messages the client sent. No handoff prompt and no partial think.
                glm_content, glm_think, llm_usage, glm_tool_calls, _llm_logprobs = await call_openai_chat(
                    self.llm,
                    openai_messages,
                    max_tokens=max_tokens,
                    tools=tools_schema,
                    sampling=self._llm_sampling or None,
                    reasoning_effort=self.llm_reasoning_effort,
                )
                llm_text = glm_content or ""
                llm_think_text = glm_think or ""
                if glm_content.startswith("[Error:"):
                    logger.error("sid=%s LLM error: %s", sid, glm_content[:500])
                if llm_usage is not None:
                    try:
                        llm_prompt_tok, llm_completion_tok = require_usage_tokens(llm_usage, where=f"LLM sid={sid}")
                    except RuntimeError:
                        logger.error("sid=%s LLM response missing/incomplete usage: %r", sid, llm_usage)
                        raise
                elif not glm_content.startswith("[Error:"):
                    logger.error("sid=%s LLM response missing/incomplete usage: %r", sid, llm_usage)
                    raise RuntimeError(f"LLM sid={sid} missing usage")
                offloaded = True
                content = glm_content or ""
                think = glm_think or ""
                tool_calls = list(glm_tool_calls or [])
                logger.info(
                    "sid=%s entropy route LLM rewrite mean=%s n=%d threshold=%.4f "
                    "slm_p=%d slm_c=%d llm_max=%s (%.1fs)",
                    sid,
                    entropy_text,
                    scored.n_tokens,
                    self.entropy_threshold,
                    slm_prompt_tok,
                    slm_out_tok,
                    max_tokens if max_tokens is not None else "remaining",
                    time.monotonic() - t0,
                )
        else:
            logger.info(
                "sid=%s keep SLM mean=%s n=%d threshold=%.4f unavailable=%s (%.1fs)",
                sid,
                entropy_text,
                scored.n_tokens,
                self.entropy_threshold,
                scored.unavailable,
                time.monotonic() - t0,
            )

        self.stats.append_turn_trace(
            {
                "time": round(time.time(), 3),
                "sid": sid,
                "task": session.task_label or session.instance_hint or sid,
                "turn": turn_idx,
                "offloaded": bool(offloaded),
                "mean_think_entropy": None if scored.mean is None else round(float(scored.mean), 6),
                "think_tokens": scored.n_tokens,
                "entropy_top_k": self.entropy_top_k,
                "entropy_unavailable": scored.unavailable,
                "slm_thinking": slm_think or "",
                "slm_output": slm_content or "",
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
            mean_think_entropy_value=scored.mean,
            think_tokens=scored.n_tokens,
            entropy_unavailable=scored.unavailable,
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
