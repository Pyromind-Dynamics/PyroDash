# SPDX-License-Identifier: Apache-2.0
"""Minimal HTTP server: dual upstream APIs → one OpenAI-compatible endpoint."""

from __future__ import annotations

import argparse
import json
import logging
import os
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn

from .core.settings import DEFAULT_OFFLOAD_TOKENS
from .engine import CollaborateEngine

logger = logging.getLogger(__name__)


def _pick(args: argparse.Namespace, *names: str, default: str | None = None) -> str | None:
    for name in names:
        val = getattr(args, name, None)
        if val:
            return str(val)
        env = os.environ.get(name.upper()) or os.environ.get(name)
        if env:
            return env
    return default


def _engine_from_env_and_args(args: argparse.Namespace) -> CollaborateEngine:
    slm_base = _pick(args, "slm_base_url", "SLM_BASE_URL", "SMALL_BASE_URL")
    slm_model = _pick(args, "slm_model", "SLM_MODEL", "SMALL_MODEL")
    llm_base = _pick(args, "llm_base_url", "LLM_BASE_URL", "LARGE_BASE_URL")
    llm_model = _pick(args, "llm_model", "LLM_MODEL", "LARGE_MODEL")
    missing = [
        n
        for n, v in [
            ("--slm-base-url / SLM_BASE_URL", slm_base),
            ("--slm-model / SLM_MODEL", slm_model),
            ("--llm-base-url / LLM_BASE_URL", llm_base),
            ("--llm-model / LLM_MODEL", llm_model),
        ]
        if not v
    ]
    if missing:
        raise SystemExit("Missing required config:\n  - " + "\n  - ".join(missing))

    tokens_raw = _pick(args, "offload_tokens", "OFFLOAD_TOKENS")
    if tokens_raw:
        tokens = [t.strip() for t in tokens_raw.split(",") if t.strip()]
    else:
        tokens = list(DEFAULT_OFFLOAD_TOKENS)

    run_mode = _pick(args, "run_mode", "RUN_MODE", default="auto_offload") or "auto_offload"
    if run_mode not in ("remote", "local", "auto_offload", "tokenSaving"):
        run_mode = "auto_offload"

    return CollaborateEngine(
        small_base_url=slm_base or "",
        small_model=slm_model or "",
        small_api_key=_pick(args, "slm_api_key", "SLM_API_KEY", "SMALL_API_KEY", default="EMPTY")
        or "EMPTY",
        large_base_url=llm_base or "",
        large_model=llm_model or "",
        large_api_key=_pick(args, "llm_api_key", "LLM_API_KEY", "LARGE_API_KEY", default="EMPTY")
        or "EMPTY",
        exposed_model_name=_pick(args, "exposed_model", "EXPOSED_MODEL_NAME", default="pyrodash")
        or "pyrodash",
        run_mode=run_mode,  # type: ignore[arg-type]
        offload_tokens=tokens,
        global_max_tokens=int(
            _pick(args, "max_tokens", "GLOBAL_MAX_TOKENS", default="8192") or "8192"
        ),
    )


def _extract_api_key(request: Request) -> str | None:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return (request.headers.get("x-api-key") or "").strip() or None


def create_app(engine: CollaborateEngine, *, api_key: str) -> FastAPI:
    app = FastAPI(title="PyroDash Collaborate Engine", version="0.1.0")
    app.state.engine = engine
    app.state.api_key = api_key

    def _require_api_key(request: Request) -> None:
        expected = (app.state.api_key or "").strip()
        if not expected:
            raise HTTPException(status_code=500, detail="server api key not configured")
        got = _extract_api_key(request)
        if got != expected:
            raise HTTPException(status_code=401, detail="invalid api key")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/v1/models")
    async def models(request: Request) -> dict[str, Any]:
        _require_api_key(request)
        return {
            "object": "list",
            "data": [
                {
                    "id": engine.config.exposed_model_name,
                    "object": "model",
                    "owned_by": "pyrodash",
                }
            ],
        }

    @app.post("/v1/chat/completions")
    async def chat(request: Request) -> Any:
        _require_api_key(request)
        try:
            body = await request.json()
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}") from exc

        messages = body.get("messages")
        if not isinstance(messages, list) or not messages:
            raise HTTPException(status_code=400, detail="messages is required")

        stream = bool(body.get("stream", False))
        kwargs = {
            "messages": messages,
            "max_tokens": body.get("max_tokens"),
            "temperature": body.get("temperature"),
            "top_p": body.get("top_p"),
            "stop": body.get("stop"),
        }

        if stream:

            async def event_gen():
                gen = await engine.chat_completions(stream=True, **kwargs)
                async for chunk in gen:
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

            return StreamingResponse(event_gen(), media_type="text/event-stream")

        try:
            result = await engine.chat_completions(stream=False, **kwargs)
        except Exception as exc:
            logger.exception("chat failed")
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        return JSONResponse(result)

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="PyroDash Collaborate Engine server")
    parser.add_argument("--slm-base-url", default=None)
    parser.add_argument("--slm-api-key", default=None)
    parser.add_argument("--slm-model", default=None)
    parser.add_argument("--llm-base-url", default=None)
    parser.add_argument("--llm-api-key", default=None)
    parser.add_argument("--llm-model", default=None)
    parser.add_argument("--exposed-model", default=None)
    parser.add_argument("--api-key", default=None, help="API key required by clients")
    parser.add_argument("--run-mode", default=None)
    parser.add_argument("--offload-tokens", default=None)
    parser.add_argument("--max-tokens", default=None)
    parser.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8100")))
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    engine = _engine_from_env_and_args(args)
    api_key = (
        _pick(args, "api_key", "EXPOSED_API_KEY", "API_KEY", default="sk-pyrodash")
        or "sk-pyrodash"
    )
    app = create_app(engine, api_key=api_key)
    logger.info(
        "Serving %s  (slm=%s → llm=%s) on http://%s:%s/v1",
        engine.config.exposed_model_name,
        engine.config.small.model,
        engine.config.large.model,
        args.host,
        args.port,
    )
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
