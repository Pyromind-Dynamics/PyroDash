from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

import httpx
from fastapi import FastAPI, HTTPException

from app.config import Settings
from app.engine import CollaborateEngine, UpstreamError
from app.models import ChatCompletionRequest, ChatCompletionResponse, TokenUsage


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = Settings.from_env()
    client = httpx.AsyncClient(timeout=settings.request_timeout_seconds)
    app.state.engine = CollaborateEngine(settings, client)
    yield
    await client.aclose()


app = FastAPI(title="PyroDash Serving", version="0.1.0", lifespan=lifespan)


@app.get("/health/live")
async def live() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest) -> ChatCompletionResponse:
    if request.stream:
        raise HTTPException(
            status_code=400,
            detail="stream=true is not implemented in the initial engine skeleton",
        )

    try:
        content, finish_reason, pyro_usage = await app.state.engine.complete(request)
    except UpstreamError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    total_usage = TokenUsage(
        prompt_tokens=pyro_usage.slm.prompt_tokens
        + (pyro_usage.llm.prompt_tokens if pyro_usage.llm else 0),
        completion_tokens=pyro_usage.slm.completion_tokens
        + (pyro_usage.llm.completion_tokens if pyro_usage.llm else 0),
    )
    total_usage.total_tokens = total_usage.prompt_tokens + total_usage.completion_tokens

    return ChatCompletionResponse(
        id=f"chatcmpl-{uuid.uuid4().hex}",
        created=int(time.time()),
        model=request.model,
        choices=[
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": finish_reason,
            }
        ],
        usage=total_usage,
        pyrodash_usage=pyro_usage,
    )
