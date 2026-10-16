"""Mean top-k entropy of the small model's thinking tokens.

For each generated token i with top-k logprobs {ℓ_j}:

    p_j = exp(ℓ_j) / Σ_k exp(ℓ_k)
    H_i = -Σ_j p_j * ln(p_j)     # nats, range [0, ln(k)]

The route score is the mean of H_i over tokens strictly inside thinking.
The Qwen chat template already opens ``<think>`` in the prompt, so a
generation that never emits ``<think>`` is treated as thinking until
``</think>`` (or until the end, if the close tag is missing).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

THINK_OPEN = "<think>"
THINK_CLOSE = "</think>"


def _as_logprob(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        lp = float(value)
        return lp if math.isfinite(lp) else None
    if isinstance(value, dict):
        if "logprob" in value:
            return _as_logprob(value.get("logprob"))
        if "logprobs" in value:
            return _as_logprob(value.get("logprobs"))
    return None


def top_logprob_values(entry: Any, *, top_k: int) -> list[float]:
    """Highest ``top_k`` logprobs at one generated position."""
    if not isinstance(entry, dict):
        lp = _as_logprob(entry)
        values = [lp] if lp is not None else []
    else:
        top = entry.get("top_logprobs")
        values: list[float] = []
        if isinstance(top, list):
            for item in top:
                lp = _as_logprob(item)
                if lp is not None:
                    values.append(lp)
        elif isinstance(top, dict):
            for value in top.values():
                lp = _as_logprob(value)
                if lp is not None:
                    values.append(lp)
        if not values:
            chosen = _as_logprob(entry.get("logprob"))
            values = [chosen] if chosen is not None else []
    if top_k > 0 and len(values) > top_k:
        values = sorted(values, reverse=True)[:top_k]
    return values


def token_entropy_nats(logprobs: list[float]) -> float | None:
    """Entropy after softmax over the given logprobs."""
    if not logprobs:
        return None
    finite = [lp for lp in logprobs if math.isfinite(lp)]
    if not finite:
        return None
    maximum = max(finite)
    weights = [math.exp(lp - maximum) for lp in finite]
    total = sum(weights)
    if total <= 0.0:
        return None
    entropy = 0.0
    for weight in weights:
        p = weight / total
        if p > 0.0:
            entropy -= p * math.log(p)
    return entropy


def _token_text(entry: Any) -> str:
    if isinstance(entry, dict) and entry.get("token") is not None:
        return str(entry.get("token"))
    return ""


def iter_token_entries(logprobs: Any) -> list[tuple[str, Any]]:
    """``(source, entry)`` pairs. source is content / reasoning_content / reasoning."""
    if logprobs is None:
        return []
    if isinstance(logprobs, list):
        return [("content", item) for item in logprobs if item is not None]
    if not isinstance(logprobs, dict):
        return []
    out: list[tuple[str, Any]] = []
    for key in ("reasoning_content", "reasoning", "content"):
        items = logprobs.get(key)
        if isinstance(items, list):
            out.extend((key, item) for item in items if item is not None)
    return out


def thinking_interior_spans(text: str) -> list[tuple[int, int]]:
    """Character span of this turn's thinking, exclusive of the tags.

    The Qwen template opens ``<think>`` in the prompt, so generated text is
    inside thinking until the first ``</think>``. A ``<think>`` emitted by
    the model before that close moves the start to just after the tag.
    A ``<think>`` that appears only in the answer (after the close) is ignored.
    If the close tag is missing, the rest of the generation stays inside thinking.
    """
    if not text:
        return []
    close_at = text.find(THINK_CLOSE)
    open_at = text.find(THINK_OPEN)
    if close_at < 0:
        if open_at < 0:
            return [(0, len(text))]
        start = open_at + len(THINK_OPEN)
        return [(start, len(text))] if start < len(text) else []
    if open_at >= 0 and open_at < close_at:
        start = open_at + len(THINK_OPEN)
    else:
        start = 0
    if start >= close_at:
        return []
    return [(start, close_at)]


def _overlaps(start: int, end: int, spans: list[tuple[int, int]]) -> bool:
    if end <= start:
        return False
    for a, b in spans:
        if start < b and end > a:
            return True
    return False


@dataclass(frozen=True)
class ThinkEntropy:
    mean: float | None
    n_tokens: int
    unavailable: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "mean": None if self.mean is None else round(float(self.mean), 6),
            "n_tokens": self.n_tokens,
            "unavailable": self.unavailable,
        }


def mean_think_entropy(logprobs: Any, *, top_k: int = 20) -> ThinkEntropy:
    """Average per-token top-k entropy over thinking-interior tokens."""
    pairs = iter_token_entries(logprobs)
    if not pairs:
        return ThinkEntropy(mean=None, n_tokens=0, unavailable=True)

    reasoning_pairs = [pair for pair in pairs if pair[0] in ("reasoning", "reasoning_content")]
    if reasoning_pairs:
        selected = reasoning_pairs
    else:
        content_pairs = [pair for pair in pairs if pair[0] == "content"]
        texts = [_token_text(entry) for _, entry in content_pairs]
        joined = "".join(texts)
        spans = thinking_interior_spans(joined)
        cursor = 0
        selected = []
        for pair, text in zip(content_pairs, texts):
            start = cursor
            cursor += len(text)
            if _overlaps(start, cursor, spans):
                selected.append(pair)

    entropies: list[float] = []
    for _, entry in selected:
        entropy = token_entropy_nats(top_logprob_values(entry, top_k=top_k))
        if entropy is not None:
            entropies.append(entropy)
    if not entropies:
        return ThinkEntropy(mean=None, n_tokens=0, unavailable=True)
    return ThinkEntropy(
        mean=sum(entropies) / len(entropies),
        n_tokens=len(entropies),
        unavailable=False,
    )


def should_route(mean_entropy: float | None, threshold: float) -> bool:
    """Route to the large model when thinking entropy is strictly above the threshold."""
    if mean_entropy is None:
        return False
    return float(mean_entropy) > float(threshold)
