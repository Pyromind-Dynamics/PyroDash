"""Shared HTTP/protocol helpers for tag and entropy adapters.

Runtime code under ``tag/`` and ``entropy/`` stays self-contained for
independent launches. This package holds the merged reference copies
(``protocol``, ``openai_api`` with optional logprobs, ``stats``, ``tools``).
"""

from .openai_api import EndpointConfig, call_openai_chat, call_openai_chat_sync

__all__ = ["EndpointConfig", "call_openai_chat", "call_openai_chat_sync"]
