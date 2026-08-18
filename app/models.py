from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="allow")

    model: str = "pyrodash"
    messages: list[ChatMessage]
    max_tokens: int = Field(default=8192, gt=0)
    temperature: float = Field(default=0.1, ge=0)
    stream: bool = False


class TokenUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class PyroDashUsage(BaseModel):
    offloaded: bool
    slm: TokenUsage
    llm: TokenUsage | None = None


class ChatCompletionResponse(BaseModel):
    id: str
    object: Literal["chat.completion"] = "chat.completion"
    created: int
    model: str
    choices: list[dict[str, Any]]
    usage: TokenUsage
    pyrodash_usage: PyroDashUsage
