#!/usr/bin/env python3
"""Entropy-routed offload adapter for Pier DeepSWE / mini-swe-agent.

All logic lives under ``eval/offload_entropy`` (no imports from other trees).

pier → OpenAI /v1/chat/completions → this server → SLM, then LLM only when
the mean top-k entropy of the SLM thinking tokens is above ``--entropy-threshold``.
On a route, the SLM thinking is dropped and the LLM rewrites the turn.
Anthropic /v1/messages remains available for back-compat.

Online stats (per turn): turns, offload_count, mean_think_entropy, SLM/LLM
prompt+completion tokens from API ``usage``. Written under ``--stats-dir``.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from aiohttp import web  # noqa: E402

from adapter import EndpointConfig, OffloadAdapter  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("deep_swe.offload.adapter")


def _parse_bool(value: str) -> bool:
    text = str(value).strip().lower()
    if text in ("1", "true", "yes", "on", "y"):
        return True
    if text in ("0", "false", "no", "off", "n"):
        return False
    raise argparse.ArgumentTypeError(f"expected bool, got {value!r}")


def _parse_int_list(value: str | None) -> list[int] | None:
    if value is None or not str(value).strip():
        return None
    out: list[int] = []
    for part in str(value).replace(";", ",").split(","):
        part = part.strip()
        if part:
            out.append(int(part))
    return out or None


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default=os.environ.get("ADAPTER_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("ADAPTER_PORT", "18022")))
    p.add_argument("--slm-base-url", default=os.environ.get("SLM_BASE_URL", "http://127.0.0.1:8001/v1"))
    p.add_argument("--slm-api-key", default=os.environ.get("SLM_API_KEY", "dummy"))
    p.add_argument("--slm-model", default=os.environ.get("SLM_MODEL", "slm"))
    p.add_argument("--llm-base-url", default=os.environ.get("LLM_BASE_URL", ""))
    p.add_argument("--llm-api-key", default=os.environ.get("LLM_API_KEY", ""))
    p.add_argument("--llm-model", default=os.environ.get("LLM_MODEL", "deepseek-v4.1-flash"))
    p.add_argument("--use-llm", type=_parse_bool, default=_parse_bool(os.environ.get("USE_LLM", "true")))
    p.add_argument(
        "--max-new-tokens",
        type=int,
        default=int(os.environ.get("MAX_NEW_TOKENS", "8192")),
        help="per-call completion budget. SLM is capped at this; an LLM rewrite gets the same full budget because the SLM turn is discarded. 0 = no cap",
    )
    p.add_argument(
        "--max-context-len",
        type=int,
        default=int(os.environ.get("MAX_CONTEXT_LEN", "0")),
        help="context window used when reading overflow errors; 0 = do not assume one",
    )
    p.add_argument("--slm-stop-token-ids", default=os.environ.get("SLM_STOP_TOKEN_IDS", ""))
    p.add_argument(
        "--slm-skip-special-tokens",
        default=os.environ.get("SLM_SKIP_SPECIAL_TOKENS", ""),
        help="empty=omit; true/false passed to SLM",
    )
    p.add_argument(
        "--stats-dir",
        default=os.environ.get("ADAPTER_STATS_DIR", ""),
        help="directory for online adapter_stats (summary.json + sessions/*.json)",
    )
    p.add_argument(
        "--slm-temperature",
        type=float,
        default=float(os.environ.get("SLM_TEMPERATURE", "1.0")),
    )
    p.add_argument("--slm-top-p", type=float, default=float(os.environ.get("SLM_TOP_P", "0.95")))
    p.add_argument("--slm-top-k", type=int, default=int(os.environ.get("SLM_TOP_K", "20")))
    p.add_argument("--slm-min-p", type=float, default=float(os.environ.get("SLM_MIN_P", "0.0")))
    p.add_argument(
        "--slm-presence-penalty",
        type=float,
        default=float(os.environ.get("SLM_PRESENCE_PENALTY", "1.5")),
    )
    p.add_argument(
        "--slm-repetition-penalty",
        type=float,
        default=float(os.environ.get("SLM_REPETITION_PENALTY", "1.0")),
    )
    p.add_argument(
        "--llm-temperature",
        type=float,
        default=float(os.environ.get("LLM_TEMPERATURE", "1.0")),
    )
    p.add_argument("--llm-top-p", type=float, default=float(os.environ.get("LLM_TOP_P", "1.0")))
    p.add_argument(
        "--entropy-threshold",
        type=float,
        default=float(os.environ.get("ENTROPY_THRESHOLD", "0.5")),
        help="route to the LLM when mean thinking entropy (nats) is strictly greater than this",
    )
    p.add_argument(
        "--entropy-top-k",
        type=int,
        default=int(os.environ.get("ENTROPY_TOP_K", "20")),
        help="top-k logprobs used for each thinking-token entropy",
    )
    p.add_argument(
        "--llm-reasoning-effort",
        default=os.environ.get("LLM_REASONING_EFFORT", "high"),
        help="reasoning_effort for the LLM rewrite; empty disables the field",
    )
    args = p.parse_args()

    slm = EndpointConfig(base_url=args.slm_base_url, api_key=args.slm_api_key, model=args.slm_model)
    if args.use_llm:
        if not (args.llm_base_url and args.llm_api_key and args.llm_model):
            raise SystemExit("USE_LLM=true requires --llm-base-url --llm-api-key --llm-model")
        llm = EndpointConfig(base_url=args.llm_base_url, api_key=args.llm_api_key, model=args.llm_model)
    else:
        llm = EndpointConfig(base_url="http://127.0.0.1:0/v1", api_key="unused", model="unused")

    skip: bool | None = None
    if str(args.slm_skip_special_tokens).strip():
        skip = _parse_bool(args.slm_skip_special_tokens)

    stats_dir = str(args.stats_dir).strip() or None
    slm_sampling = {
        "temperature": args.slm_temperature,
        "top_p": args.slm_top_p,
        "presence_penalty": args.slm_presence_penalty,
        "extra_body": {
            "top_k": args.slm_top_k,
            "min_p": args.slm_min_p,
            "repetition_penalty": args.slm_repetition_penalty,
        },
    }
    llm_sampling = {"temperature": args.llm_temperature, "top_p": args.llm_top_p}
    adapter = OffloadAdapter(
        slm=slm,
        llm=llm,
        use_llm=bool(args.use_llm),
        slm_stop_token_ids=_parse_int_list(args.slm_stop_token_ids),
        slm_skip_special_tokens=skip,
        sampling_defaults={
            "max_new_tokens": args.max_new_tokens,
        },
        slm_sampling=slm_sampling,
        llm_sampling=llm_sampling,
        max_context_tokens=args.max_context_len,
        stats_dir=stats_dir,
        entropy_threshold=args.entropy_threshold,
        entropy_top_k=args.entropy_top_k,
        llm_reasoning_effort=str(args.llm_reasoning_effort),
    )

    logger.info(
        "adapter listening on %s:%s | SLM=%s @ %s | LLM=%s @ %s | use_llm=%s | "
        "max_new_tokens=%s | entropy_threshold=%s | entropy_top_k=%s | "
        "llm_reasoning_effort=%s | stats_dir=%s | slm_sampling=%s | llm_sampling=%s",
        args.host,
        args.port,
        slm.model,
        slm.normalized_base(),
        llm.model,
        llm.normalized_base(),
        args.use_llm,
        args.max_new_tokens if args.max_new_tokens > 0 else "unlimited",
        args.entropy_threshold,
        args.entropy_top_k,
        args.llm_reasoning_effort or "(default)",
        stats_dir,
        slm_sampling,
        llm_sampling,
    )
    web.run_app(
        adapter.app,
        host=args.host,
        port=args.port,
        handler_cancellation=True,
    )


if __name__ == "__main__":
    main()
