#!/usr/bin/env python3
"""Standalone offload adapter for Pier DeepSWE / mini-swe-agent.

All logic lives under ``eval/offload`` (no imports from other trees).

pier → OpenAI /v1/chat/completions → this server → SLM (+ optional LLM).
Anthropic /v1/messages remains available for back-compat.

Online stats (per turn): turns, offload_count, SLM/LLM prompt+completion tokens
from API ``usage``. Written under ``--stats-dir`` after every request.
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
    # Default: offload handoff needs stop=true; SLM-only usually wants false so generation can reach tool_calls.
    _use_llm_default = _parse_bool(os.environ.get("USE_LLM", "true"))
    _stop_env = os.environ.get("STOP_ON_OFFLOAD_CLOSE", "").strip()
    if _stop_env:
        _stop_default = _parse_bool(_stop_env)
    else:
        _stop_default = bool(_use_llm_default)
    p.add_argument(
        "--stop-on-offload-close",
        type=_parse_bool,
        default=_stop_default,
        help="if true, pass <|/llm_offload|> as SLM stop; default false when USE_LLM=false",
    )
    p.add_argument(
        "--max-new-tokens",
        type=int,
        default=int(os.environ.get("MAX_NEW_TOKENS", "8192")),
        help="shared per-turn SLM+LLM completion budget; LLM gets budget-slm_completion; 0 = no shared cap",
    )
    p.add_argument("--max-context-len", type=int, default=int(os.environ.get("MAX_CONTEXT_LEN", "128000")))
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
        "--offload-mode",
        default=os.environ.get("OFFLOAD_MODE", "rewrite"),
        choices=("handoff", "rewrite", "keep"),
        help="rewrite: drop SLM and regenerate; handoff: part_think continue; keep: keep SLM text without part_think",
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
        stop_on_offload_close=bool(args.stop_on_offload_close),
        slm_stop_token_ids=_parse_int_list(args.slm_stop_token_ids),
        slm_skip_special_tokens=skip,
        sampling_defaults={
            "max_new_tokens": args.max_new_tokens,
        },
        slm_sampling=slm_sampling,
        llm_sampling=llm_sampling,
        max_context_tokens=args.max_context_len,
        stats_dir=stats_dir,
        offload_mode=args.offload_mode,
    )

    logger.info(
        "adapter listening on %s:%s | SLM=%s @ %s | LLM=%s @ %s | use_llm=%s | "
        "stop_on_offload_close=%s | offload_mode=%s | max_new_tokens=%s | stats_dir=%s | "
        "slm_sampling=%s | llm_sampling=%s",
        args.host,
        args.port,
        slm.model,
        slm.normalized_base(),
        llm.model,
        llm.normalized_base(),
        args.use_llm,
        args.stop_on_offload_close,
        args.offload_mode,
        args.max_new_tokens if args.max_new_tokens > 0 else "unlimited",
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
