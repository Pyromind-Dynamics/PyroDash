# SPDX-License-Identifier: Apache-2.0
"""PyroDash Collaborate Engine — dual OpenAI APIs in, one chat API out."""

from .core import (
    CollaborativeSettings,
    EndpointConfig,
    EngineConfig,
    OffloadDetector,
    build_remote_messages,
)
from .engine import CollaborateEngine
from .server import create_app, main as serve

__all__ = [
    "CollaborateEngine",
    "CollaborativeSettings",
    "EndpointConfig",
    "EngineConfig",
    "OffloadDetector",
    "build_remote_messages",
    "create_app",
    "serve",
]

__version__ = "0.1.0"
