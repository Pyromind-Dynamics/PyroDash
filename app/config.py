from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    sglang_base_url: str
    sglang_model: str
    glm_base_url: str | None
    glm_api_key: str | None
    glm_model: str | None
    request_timeout_seconds: float

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            sglang_base_url=os.getenv("SGLANG_BASE_URL", "http://127.0.0.1:30000/v1"),
            sglang_model=os.getenv("SGLANG_MODEL", "pyrodash-small"),
            glm_base_url=os.getenv("GLM_BASE_URL"),
            glm_api_key=os.getenv("GLM_API_KEY"),
            glm_model=os.getenv("GLM_MODEL"),
            request_timeout_seconds=float(os.getenv("REQUEST_TIMEOUT_SECONDS", "600")),
        )
