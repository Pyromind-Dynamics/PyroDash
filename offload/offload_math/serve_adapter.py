#!/usr/bin/env python3
"""Launch the math offload adapter HTTP server."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    v = str(value).strip().lower()
    if v in ("1", "true", "yes", "y", "on"):
        return True
    if v in ("0", "false", "no", "n", "off"):
        return False
    raise argparse.ArgumentTypeError(f"expected bool, got {value!r}")


def main() -> None:
    root = Path(__file__).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    p = argparse.ArgumentParser(description="Math offload adapter (completions + bare <|llm_offload|>)")
    p.add_argument("--host", default=os.environ.get("ADAPTER_HOST", "0.0.0.0"))
    p.add_argument("--port", type=int, default=int(os.environ.get("ADAPTER_PORT", "18031")))
    p.add_argument("--tokenizer-path", required=True, help="HF model dir for chat template / vocab")
    p.add_argument("--slm-base-url", required=True)
    p.add_argument("--slm-api-key", default="dummy")
    p.add_argument("--slm-model", required=True)
    p.add_argument("--llm-base-url", default=os.environ.get("LLM_BASE_URL", "http://127.0.0.1:0/v1"))
    p.add_argument("--llm-api-key", default=os.environ.get("LLM_API_KEY", "unused"))
    p.add_argument("--llm-model", default=os.environ.get("LLM_MODEL", "unused"))
    p.add_argument("--use-llm", type=_parse_bool, default=_parse_bool(os.environ.get("USE_LLM", "true")))
    p.add_argument("--slm-temperature", type=float, default=0.1)
    p.add_argument("--llm-temperature", type=float, default=1.0)
    p.add_argument("--llm-top-p", type=float, default=1.0)
    p.add_argument("--max-new-tokens", type=int, default=8192)
    p.add_argument("--stats-dir", default="")
    args = p.parse_args()

    if args.use_llm:
        if not args.llm_base_url or not args.llm_api_key or not args.llm_model:
            raise SystemExit("USE_LLM=true requires --llm-base-url --llm-api-key --llm-model")

    from adapter.server import MathOffloadEngine, create_app
    import uvicorn

    stats_dir = Path(args.stats_dir).resolve() if args.stats_dir else None
    engine = MathOffloadEngine(
        tokenizer_path=args.tokenizer_path,
        slm_base_url=args.slm_base_url,
        slm_api_key=args.slm_api_key,
        slm_model=args.slm_model,
        llm_base_url=args.llm_base_url,
        llm_api_key=args.llm_api_key,
        llm_model=args.llm_model,
        use_llm=args.use_llm,
        slm_temperature=args.slm_temperature,
        llm_temperature=args.llm_temperature,
        llm_top_p=args.llm_top_p,
        default_max_tokens=args.max_new_tokens,
        stats_dir=stats_dir,
    )
    app = create_app(engine)
    print(
        f"[math-adapter] listen http://{args.host}:{args.port}/  "
        f"use_llm={args.use_llm} slm={args.slm_model} @ {args.slm_base_url}",
        flush=True,
    )
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
