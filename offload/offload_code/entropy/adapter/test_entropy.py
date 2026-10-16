"""Checks for thinking-span entropy and the LLM rewrite history."""

from __future__ import annotations

import math
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from adapter.entropy import mean_think_entropy, should_route, token_entropy_nats  # noqa: E402


def almost(a: float, b: float, eps: float = 1e-9) -> bool:
    return abs(a - b) < eps


def _tok(text: str, logprobs: list[float]) -> dict:
    return {
        "token": text,
        "logprob": logprobs[0],
        "top_logprobs": [{"token": f"t{i}", "logprob": lp} for i, lp in enumerate(logprobs)],
    }


def test_token_entropy() -> None:
    peaked = token_entropy_nats([0.0])
    assert peaked is not None and almost(peaked, 0.0)
    two = token_entropy_nats([0.0, 0.0])
    assert two is not None and almost(two, math.log(2))


def test_prompt_opened_think_excludes_answer() -> None:
    # Template already wrote <think>. Answer after </think> must not count,
    # even if the answer itself contains the string "<think>".
    logprobs = {
        "content": [
            _tok("un", [0.0, 0.0]),
            _tok("sure", [0.0, 0.0]),
            _tok("</think>", [0.0]),
            _tok("\nanswer <think> later", [0.0, 0.0, 0.0]),
        ]
    }
    scored = mean_think_entropy(logprobs, top_k=20)
    assert scored.n_tokens == 2
    assert scored.mean is not None and almost(scored.mean, math.log(2))
    assert should_route(scored.mean, 0.5)
    assert not should_route(scored.mean, math.log(2))
    assert not should_route(None, 0.5)


def test_explicit_think_tag_and_unclosed() -> None:
    opened = {
        "content": [
            _tok("<think>", [0.0]),
            _tok("hmm", [0.0]),
            _tok("</think>", [0.0]),
            _tok("go", [0.0, 0.0]),
        ]
    }
    scored = mean_think_entropy(opened, top_k=20)
    assert scored.n_tokens == 1
    assert scored.mean is not None and almost(scored.mean, 0.0)

    unclosed = {"content": [_tok("still", [0.0, 0.0]), _tok(" thinking", [0.0])]}
    scored = mean_think_entropy(unclosed, top_k=20)
    assert scored.n_tokens == 2
    assert scored.mean is not None and almost(scored.mean, math.log(2) / 2)


def test_reasoning_channel_only() -> None:
    logprobs = {
        "reasoning_content": [_tok("think", [0.0, 0.0])],
        "content": [_tok("bash", [0.0])],
    }
    scored = mean_think_entropy(logprobs, top_k=20)
    assert scored.n_tokens == 1
    assert scored.mean is not None and almost(scored.mean, math.log(2))


def test_top_k_uses_highest() -> None:
    # 21 equal masses would be ln(21); top 20 renormalizes to ln(20).
    logprobs = {"content": [_tok("x", [0.0] * 21), _tok("</think>", [0.0])]}
    scored = mean_think_entropy(logprobs, top_k=20)
    assert scored.mean is not None and almost(scored.mean, math.log(20))


def main() -> None:
    test_token_entropy()
    test_prompt_opened_think_excludes_answer()
    test_explicit_think_tag_and_unclosed()
    test_reasoning_channel_only()
    test_top_k_uses_highest()
    print("entropy routing checks ok")


if __name__ == "__main__":
    main()
