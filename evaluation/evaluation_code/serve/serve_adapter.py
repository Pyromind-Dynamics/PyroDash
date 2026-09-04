#!/usr/bin/env python3
"""Standalone Anthropic offload adapter for mini-extra swebench.

All logic lives under ``evaluation_code/adapter``.

mini-extra → Anthropic /v1/messages → this server → SLM (+ optional LLM).

Online stats (per turn): turns, offload_count, SLM/LLM prompt+completion tokens
from API ``usage``. Written under ``--stats-dir`` after every request.

SLM / LLM sampling come from YAML under ``serve/config_yaml/`` (any key is
forwarded to the OpenAI-compatible client).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_SERVE_DIR = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import yaml  # noqa: E402
from aiohttp import web  # noqa: E402

from adapter import EndpointConfig, OffloadAdapter  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("evaluation_code.adapter")

_DEFAULT_SLM_CONFIG = _SERVE_DIR / "config_yaml" / "slm.yaml"
_DEFAULT_LLM_CONFIG = _SERVE_DIR / "config_yaml" / "llm.yaml"


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


def _parse_max_new_tokens(value: str) -> int | str:
    text = str(value).strip()
    if text.lower() == "nolimit":
        return "nolimit"
    try:
        n = int(text)
    except ValueError as e:
        raise argparse.ArgumentTypeError(
            f"expected positive int or 'nolimit', got {value!r}"
        ) from e
    if n <= 0:
        raise argparse.ArgumentTypeError(
            "max-new-tokens must be a positive int, or 'nolimit' for no shared cap"
        )
    return n


def _load_sampling_yaml(path: str | Path) -> dict[str, Any]:
    """Load a sampling YAML mapping; empty file → {}."""
    p = Path(path).expanduser()
    if not p.is_file():
        raise SystemExit(f"sampling config not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise SystemExit(f"sampling config must be a mapping: {p}")
    # Optional wrapper: {sampling: {...}}
    if set(data.keys()) == {"sampling"} and isinstance(data["sampling"], dict):
        return dict(data["sampling"])
    return dict(data)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", default=os.environ.get("ADAPTER_HOST", "127.0.0.1"))
    p.add_argument("--port", type=int, default=int(os.environ.get("ADAPTER_PORT", "18022")))
    p.add_argument("--slm-base-url", default=os.environ.get("SLM_BASE_URL", "http://127.0.0.1:8001/v1"))
    p.add_argument("--slm-api-key", default=os.environ.get("SLM_API_KEY", "dummy"))
    p.add_argument("--slm-model", default=os.environ.get("SLM_MODEL", "slm"))
    p.add_argument("--llm-base-url", default=os.environ.get("LLM_BASE_URL", ""))
    p.add_argument("--llm-api-key", default=os.environ.get("LLM_API_KEY", ""))
    p.add_argument("--llm-model", default=os.environ.get("LLM_MODEL", "deepseek-v4-flash-0731"))
    p.add_argument("--use-llm", type=_parse_bool, default=_parse_bool(os.environ.get("USE_LLM", "true")))
    p.add_argument(
        "--max-new-tokens",
        type=_parse_max_new_tokens,
        default=_parse_max_new_tokens(os.environ.get("MAX_NEW_TOKENS", "8192")),
        help=(
            "shared per-turn SLM+LLM completion budget; LLM gets budget-slm_completion; "
            "nolimit = no shared cap"
        ),
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
        "--slm-config",
        default=os.environ.get("SLM_CONFIG", str(_DEFAULT_SLM_CONFIG)),
        help="YAML of SLM sampling params forwarded to the SLM client (default: serve/config_yaml/slm.yaml)",
    )
    p.add_argument(
        "--llm-config",
        default=os.environ.get("LLM_CONFIG", str(_DEFAULT_LLM_CONFIG)),
        help="YAML of LLM sampling params forwarded to the LLM client (default: serve/config_yaml/llm.yaml)",
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
    slm_sampling = _load_sampling_yaml(args.slm_config)
    llm_sampling = _load_sampling_yaml(args.llm_config) if args.use_llm else {}
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
    )

    logger.info(
        "adapter listening on %s:%s | SLM=%s @ %s | LLM=%s @ %s | use_llm=%s | "
        "max_new_tokens=%s | stats_dir=%s | slm_config=%s %s | llm_config=%s %s",
        args.host,
        args.port,
        slm.model,
        slm.normalized_base(),
        llm.model,
        llm.normalized_base(),
        args.use_llm,
        args.max_new_tokens,
        stats_dir,
        args.slm_config,
        slm_sampling,
        args.llm_config,
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
