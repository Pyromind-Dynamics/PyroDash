# SPDX-License-Identifier: Apache-2.0
"""Core collaborative decoding primitives."""

from .handoff import (
    DEFAULT_REMOTE_HANDOFF_PROMPT,
    build_remote_messages,
    format_remote_assistant_content,
)
from .messages import append_system_message
from .offload_detector import OffloadDetector
from .settings import (
    DEFAULT_OFFLOAD_TOKENS,
    CollaborativeSettings,
    EndpointConfig,
    EngineConfig,
    collaborative_local_system_append,
)
from .thinking import ThinkingParser, extract_thinking

__all__ = [
    "DEFAULT_OFFLOAD_TOKENS",
    "DEFAULT_REMOTE_HANDOFF_PROMPT",
    "CollaborativeSettings",
    "EndpointConfig",
    "EngineConfig",
    "OffloadDetector",
    "ThinkingParser",
    "append_system_message",
    "build_remote_messages",
    "collaborative_local_system_append",
    "extract_thinking",
    "format_remote_assistant_content",
]
