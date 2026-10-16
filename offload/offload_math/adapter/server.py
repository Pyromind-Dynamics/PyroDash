"""Math offload HTTP adapter: SLM completions + stop tag + optional LLM relay."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from transformers import AutoTokenizer

from .relay import OFFLOAD_TAG, complete_offload_response
from .stats import MathStats, normalize_usage

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a helpful assistant. Solve the given problem step by step. "
    "For very difficult steps, you can output <|llm_offload|> to request help "
    "from a more capable model."
)
PROMPT_SUFFIX = (
    "\nPlease reason step by step, and put your final answer within \\boxed{}."
)


class CompleteRequest(BaseModel):
    question: str
    max_tokens: int = Field(default=8192, ge=1)


class CompleteBatchRequest(BaseModel):
    questions: list[str]
    max_tokens: int = Field(default=8192, ge=1)


class MathOffloadEngine:
    def __init__(
        self,
        *,
        tokenizer_path: str,
        slm_base_url: str,
        slm_api_key: str,
        slm_model: str,
        llm_base_url: str,
        llm_api_key: str,
        llm_model: str,
        use_llm: bool = True,
        slm_temperature: float = 0.1,
        llm_temperature: float = 1.0,
        llm_top_p: float = 1.0,
        default_max_tokens: int = 8192,
        stats_dir: Path | None = None,
    ) -> None:
        self.tokenizer = AutoTokenizer.from_pretrained(tokenizer_path, trust_remote_code=True)
        if OFFLOAD_TAG not in self.tokenizer.get_vocab():
            raise RuntimeError(f"Tokenizer missing {OFFLOAD_TAG!r} at {tokenizer_path}")
        self.slm_base_url = slm_base_url.rstrip("/")
        self.slm_api_key = slm_api_key
        self.slm_model = slm_model
        self.llm_base_url = llm_base_url.rstrip("/")
        self.llm_api_key = llm_api_key
        self.llm_model = llm_model
        self.use_llm = use_llm
        self.slm_temperature = slm_temperature
        self.llm_temperature = llm_temperature
        self.llm_top_p = llm_top_p
        self.default_max_tokens = default_max_tokens
        self.stats_dir = stats_dir
        self.stats = MathStats()

    def build_chat_messages(self, question: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": question + PROMPT_SUFFIX},
        ]

    def format_prompt(self, question: str) -> str:
        messages = self.build_chat_messages(question)
        kwargs = {"tokenize": False, "add_generation_prompt": True}
        try:
            return self.tokenizer.apply_chat_template(messages, enable_thinking=True, **kwargs)
        except TypeError:
            return self.tokenizer.apply_chat_template(messages, **kwargs)

    def call_small_completion(self, prompt: str, *, max_tokens: int) -> tuple[str, dict[str, int]]:
        url = f"{self.slm_base_url}/completions"
        headers = {
            "Authorization": f"Bearer {self.slm_api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.slm_model,
            "prompt": prompt,
            "temperature": self.slm_temperature,
            "max_tokens": max_tokens,
            "stop": [OFFLOAD_TAG],
            "include_stop_str_in_output": True,
            "skip_special_tokens": False,
        }
        resp = requests.post(url, headers=headers, json=body, timeout=600.0)
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        text = str(choice.get("text") or "")
        stop_reason = choice.get("stop_reason")
        if OFFLOAD_TAG not in text and (
            stop_reason == OFFLOAD_TAG
            or (isinstance(stop_reason, str) and OFFLOAD_TAG in stop_reason)
        ):
            text = text + OFFLOAD_TAG
        usage = normalize_usage(data.get("usage")) or {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        }
        return text, usage

    def complete(self, question: str, *, max_tokens: int | None = None) -> dict[str, Any]:
        budget = int(max_tokens if max_tokens is not None else self.default_max_tokens)
        messages = self.build_chat_messages(question)
        prompt = self.format_prompt(question)
        error = False
        try:
            raw, slm_usage = self.call_small_completion(prompt, max_tokens=budget)
        except Exception as exc:
            logger.exception("SLM completion failed")
            self.stats.record(has_offload=False, slm_usage=None, llm_usage=None, error=True)
            self.stats.persist(self.stats_dir)
            raise HTTPException(status_code=502, detail=f"SLM completion failed: {exc}") from exc

        has_offload = OFFLOAD_TAG in raw
        completed = raw
        llm_usage: dict[str, int] | None = None

        if has_offload and self.use_llm:
            slm_completion = int(slm_usage.get("completion_tokens", 0))
            glm_budget = max(0, budget - slm_completion)
            try:
                completed, raw_llm_usage = complete_offload_response(
                    raw,
                    messages,
                    api_key=self.llm_api_key,
                    base_url=self.llm_base_url,
                    model=self.llm_model,
                    max_tokens=glm_budget,
                    enable_thinking=True,
                    temperature=self.llm_temperature,
                    top_p=self.llm_top_p,
                )
                llm_usage = normalize_usage(raw_llm_usage)
            except Exception as exc:
                logger.exception("LLM relay failed")
                error = True
                completed = raw
                llm_usage = None
                # still return SLM raw so eval can continue
                logger.error("relay error: %s", exc)

        self.stats.record(
            has_offload=has_offload and self.use_llm,
            slm_usage=slm_usage,
            llm_usage=llm_usage,
            error=error,
        )
        self.stats.persist(self.stats_dir)
        return {
            "raw_response": raw,
            "completed_response": completed,
            "has_offload": has_offload,
            "slm_usage": slm_usage,
            "llm_usage": llm_usage,
        }


def create_app(engine: MathOffloadEngine) -> FastAPI:
    app = FastAPI(title="PyroDash Math Offload Adapter", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "use_llm": engine.use_llm,
            "slm_model": engine.slm_model,
            "llm_model": engine.llm_model if engine.use_llm else None,
            "offload_tag": OFFLOAD_TAG,
        }

    @app.get("/stats")
    def stats() -> dict[str, Any]:
        return engine.stats.snapshot()

    @app.post("/v1/math/complete")
    def math_complete(body: CompleteRequest) -> dict[str, Any]:
        q = (body.question or "").strip()
        if not q:
            raise HTTPException(status_code=400, detail="question is required")
        return engine.complete(q, max_tokens=body.max_tokens)

    @app.post("/v1/math/complete_batch")
    def math_complete_batch(body: CompleteBatchRequest) -> dict[str, Any]:
        if not body.questions:
            raise HTTPException(status_code=400, detail="questions is required")
        results = [engine.complete(q, max_tokens=body.max_tokens) for q in body.questions]
        return {"results": results}

    return app
