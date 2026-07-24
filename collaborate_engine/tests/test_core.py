# SPDX-License-Identifier: Apache-2.0
"""Unit tests for offload detection and handoff formatting."""

from collaborate_engine.core.handoff import (
    build_remote_messages,
    format_remote_assistant_content,
)
from collaborate_engine.core.offload_detector import OffloadDetector


def test_offload_detector_strips_token_and_triggers():
    det = OffloadDetector(["<|llm_offload|>"])
    emit, hit = det.feed("partial answer <|llm_offload|> ignored")
    assert emit == "partial answer "
    assert hit is True
    assert det.matched_token == "<|llm_offload|>"
    assert det.flush() == ""


def test_offload_detector_buffers_partial_token():
    det = OffloadDetector(["<|llm_offload|>"])
    emit1, hit1 = det.feed("hello <|llm_")
    assert hit1 is False
    emit2, hit2 = det.feed("offload|> tail")
    assert hit2 is True
    assert (emit1 + emit2) == "hello "
    assert "offload" not in (emit1 + emit2)


def test_handoff_wraps_thinking():
    partial = "<think>step1</think>answer-so-far"
    content = format_remote_assistant_content(partial)
    assert "<part_think>step1</part_think>" in content
    assert "answer-so-far" in content


def test_build_remote_messages_includes_handoff_system():
    msgs = build_remote_messages(
        [{"role": "user", "content": "q"}],
        "<think>r</think>",
    )
    roles = [m["role"] for m in msgs]
    assert "system" in roles
    assert any(m["role"] == "assistant" and "part_think" in m["content"] for m in msgs)
