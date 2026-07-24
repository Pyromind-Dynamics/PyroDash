# SPDX-License-Identifier: Apache-2.0
"""Optional helpers to build EngineConfig (library use prefers CollaborateEngine)."""

from __future__ import annotations

from typing import Sequence

from .core.settings import (
    DEFAULT_OFFLOAD_TOKENS,
    EndpointConfig,
    EngineConfig,
    RunMode,
)


def build_config(
    *,
    small_base_url: str,
    small_model: str,
    large_base_url: str,
    large_model: str,
    small_api_key: str = "EMPTY",
    large_api_key: str = "EMPTY",
    exposed_model_name: str = "pyrodash",
    run_mode: RunMode = "auto_offload",
    offload_tokens: Sequence[str] | None = None,
    global_max_tokens: int = 8192,
) -> EngineConfig:
    return EngineConfig(
        small=EndpointConfig(
            base_url=small_base_url,
            api_key=small_api_key,
            model=small_model,
        ),
        large=EndpointConfig(
            base_url=large_base_url,
            api_key=large_api_key,
            model=large_model,
        ),
        exposed_model_name=exposed_model_name,
        run_mode=run_mode,
        offload_tokens=list(offload_tokens)
        if offload_tokens is not None
        else list(DEFAULT_OFFLOAD_TOKENS),
        global_max_tokens=global_max_tokens,
    )
