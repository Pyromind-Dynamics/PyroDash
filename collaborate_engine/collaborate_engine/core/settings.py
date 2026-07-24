# SPDX-License-Identifier: Apache-2.0
"""Collaborative decoding settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

RUN_MODES = ("remote", "local", "auto_offload", "tokenSaving")
RunMode = Literal["remote", "local", "auto_offload", "tokenSaving"]

# Paper / eval token first; also accept product-style tags.
DEFAULT_OFFLOAD_TOKENS = ["<|llm_offload|>", "<llm_offload>", "</llm_offload>"]

DEFAULT_TOKEN_SAVING_PROMPT = (
    "Prefer to complete tasks independently without requesting help. "
    "Only emit an offload token when the task truly requires a larger model."
)

DEFAULT_AUTO_OFFLOAD_LOCAL_PROMPT = (
    "For very difficult steps, you can output <|llm_offload|> to request help "
    "from a more capable model."
)


@dataclass
class EndpointConfig:
    """OpenAI-compatible chat completions endpoint."""

    base_url: str
    api_key: str = "EMPTY"
    model: str = ""

    @property
    def id(self) -> str:
        return self.model

    @property
    def upstream_model(self) -> str:
        return self.model

    def chat_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


@dataclass
class EngineConfig:
    """Dual-API Collaborate Engine configuration."""

    small: EndpointConfig
    large: EndpointConfig
    exposed_model_name: str = "pyrodash"
    run_mode: RunMode = "auto_offload"
    offload_tokens: list[str] = field(
        default_factory=lambda: list(DEFAULT_OFFLOAD_TOKENS)
    )
    token_saving_prompt: str | None = None
    global_max_tokens: int = 8192

    def to_collab_settings(self) -> CollaborativeSettings:
        return CollaborativeSettings(
            run_mode=self.run_mode,
            local_model=self.small.model,
            remote_model=self.large.model,
            exposed_model_name=self.exposed_model_name,
            offload_tokens=list(self.offload_tokens),
            token_saving_prompt=self.token_saving_prompt,
            global_max_tokens=self.global_max_tokens,
        )


@dataclass
class CollaborativeSettings:
    run_mode: RunMode = "auto_offload"
    local_model: str | None = None
    remote_model: str | None = None
    exposed_model_name: str = "pyrodash"
    offload_tokens: list[str] = field(
        default_factory=lambda: list(DEFAULT_OFFLOAD_TOKENS)
    )
    token_saving_prompt: str | None = None
    global_max_tokens: int = 8192

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_mode": self.run_mode,
            "local_model": self.local_model,
            "remote_model": self.remote_model,
            "exposed_model_name": self.exposed_model_name,
            "offload_tokens": list(self.offload_tokens),
            "token_saving_prompt": self.token_saving_prompt,
            "global_max_tokens": self.global_max_tokens,
        }


def collaborative_local_system_append(collab: CollaborativeSettings) -> str | None:
    """System text to append before small-model generation."""
    custom = (collab.token_saving_prompt or "").strip()
    if collab.run_mode == "auto_offload":
        return custom or DEFAULT_AUTO_OFFLOAD_LOCAL_PROMPT
    if collab.run_mode == "tokenSaving":
        return custom or DEFAULT_TOKEN_SAVING_PROMPT
    return None
