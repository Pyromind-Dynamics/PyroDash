"""Math eval client: call offload_math adapter → score \\boxed{} → write JSON."""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests
from tqdm import tqdm

EVAL_DIR = Path(__file__).resolve().parent
if str(EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(EVAL_DIR))

import boxed_socre  # noqa: E402
import datasets_loader  # noqa: E402

DEFAULT_MAX_WORKERS = 256
OFFLOAD_TOKEN = "<|llm_offload|>"


@dataclass
class SampleRecord:
    idx: int
    question: str
    answer: str
    raw_response: str
    completed_response: str
    has_offload: bool
    score: int
    qwen_usage: dict[str, int]
    glm_usage: dict[str, int] | None


def normalize_usage(usage: dict[str, Any] | None) -> dict[str, int] | None:
    if not usage:
        return None
    p = usage.get("prompt_tokens")
    c = usage.get("completion_tokens")
    t = usage.get("total_tokens")
    if p is None and c is None and t is None:
        return None
    p, c = int(p or 0), int(c or 0)
    return {
        "prompt_tokens": p,
        "completion_tokens": c,
        "total_tokens": int(t) if t is not None else p + c,
    }


def empty_usage() -> dict[str, int]:
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


def call_adapter_complete(
    question: str,
    *,
    adapter_base: str,
    max_tokens: int,
    timeout: float = 600.0,
) -> dict[str, Any]:
    url = f"{adapter_base.rstrip('/')}/v1/math/complete"
    resp = requests.post(
        url,
        json={"question": question, "max_tokens": max_tokens},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()


def build_records(
    questions: list[str],
    answers: list[str],
    payloads: list[dict[str, Any]],
) -> list[SampleRecord]:
    records: list[SampleRecord] = []
    for idx, (question, answer, data) in enumerate(zip(questions, answers, payloads)):
        raw = str(data.get("raw_response") or "")
        completed = str(data.get("completed_response") or raw)
        has_offload = bool(data.get("has_offload", OFFLOAD_TOKEN in raw))
        slm = normalize_usage(data.get("slm_usage")) or empty_usage()
        llm = normalize_usage(data.get("llm_usage"))
        records.append(
            SampleRecord(
                idx=idx,
                question=question,
                answer=answer,
                raw_response=raw,
                completed_response=completed,
                has_offload=has_offload,
                score=1 if boxed_socre.compare_answer(completed, answer) else 0,
                qwen_usage=slm,
                glm_usage=llm,
            )
        )
    return records


def summarize_records(dataset: str, records: list[SampleRecord], wall_s: float) -> dict[str, Any]:
    n = len(records)
    offload = [r for r in records if r.has_offload]
    correct = [r for r in records if r.score == 1]
    return {
        "dataset": dataset,
        "enable_thinking": True,
        "total": n,
        "accuracy": sum(r.score for r in records) / max(n, 1),
        "offload_count": len(offload),
        "offload_rate": len(offload) / max(n, 1),
        "total_small_prompt_tokens": sum(r.qwen_usage["prompt_tokens"] for r in records),
        "total_small_completion_tokens": sum(r.qwen_usage["completion_tokens"] for r in records),
        "total_glm_prompt_tokens": sum((r.glm_usage or {}).get("prompt_tokens", 0) for r in records),
        "total_glm_completion_tokens": sum(
            (r.glm_usage or {}).get("completion_tokens", 0) for r in records
        ),
        "wall_s": wall_s,
        "correct": len(correct),
    }


def print_summary(summary: dict[str, Any]) -> None:
    print("=" * 60)
    print(f"  Dataset:     {summary['dataset']}")
    print(
        f"  Accuracy:    {100 * summary['accuracy']:.2f}% "
        f"({summary['correct']}/{summary['total']})"
    )
    print(
        f"  Offload:     {summary['offload_count']}/{summary['total']} "
        f"({100 * summary['offload_rate']:.1f}%)"
    )
    print("=" * 60)


def run_dataset(
    dataset_name: str,
    output_dir: Path,
    *,
    adapter_base: str,
    max_tokens: int,
    max_workers: int,
) -> dict[str, Any]:
    result_path = output_dir / f"{dataset_name}_results.json"
    handler = datasets_loader.get_dataset_handler(dataset_name)
    questions, answers = handler.load_data()

    t0 = time.perf_counter()
    payloads: list[dict[str, Any]] = [{} for _ in questions]

    def _run(idx: int) -> tuple[int, dict[str, Any]]:
        data = call_adapter_complete(
            questions[idx],
            adapter_base=adapter_base,
            max_tokens=max_tokens,
        )
        return idx, data

    workers = max(1, min(max_workers, len(questions)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_run, i) for i in range(len(questions))]
        for fut in tqdm(
            as_completed(futures),
            total=len(questions),
            desc=f"[{dataset_name}] adapter",
            unit="sample",
        ):
            idx, data = fut.result()
            payloads[idx] = data

    records = build_records(questions, answers, payloads)
    summary = summarize_records(dataset_name, records, time.perf_counter() - t0)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    with result_path.open("w", encoding="utf-8") as f:
        json.dump(
            {"summary": summary, "samples": [asdict(r) for r in records]},
            f,
            ensure_ascii=False,
            indent=2,
        )
    print_summary(summary)
    print(f"[save] {result_path}")
    return summary


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Math eval against a running offload_math adapter"
    )
    p.add_argument("--adapter-host", default="127.0.0.1")
    p.add_argument("--adapter-port", type=int, required=True)
    p.add_argument("--output-dir", default="./results")
    p.add_argument(
        "--datasets",
        nargs="+",
        default=["math", "gsm8k", "minerva", "olympiad", "aime2024", "aime2025"],
    )
    p.add_argument(
        "--max-tokens",
        type=int,
        default=8192,
        help="completion budget forwarded to adapter (SLM + LLM shared)",
    )
    p.add_argument("--max-workers", type=int, default=DEFAULT_MAX_WORKERS)
    return p.parse_args()


def main() -> None:
    args = parse_args()
    adapter_base = f"http://{args.adapter_host}:{args.adapter_port}"
    health_url = f"{adapter_base}/health"
    try:
        h = requests.get(health_url, timeout=5.0)
        h.raise_for_status()
    except Exception as exc:
        raise SystemExit(
            f"[eval ERROR] adapter not ready at {health_url}: {exc}\n"
            "  Start first: bash offload/offload_math/api.sh"
        ) from exc

    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"[config] adapter={adapter_base}")
    print(f"[config] max_tokens={args.max_tokens} workers={args.max_workers}")
    print(f"[config] output_dir={output_dir}")
    print(f"[config] datasets={args.datasets}")

    summaries = []
    for name in args.datasets:
        print(f"\n>>> {name}")
        summaries.append(
            run_dataset(
                name,
                output_dir,
                adapter_base=adapter_base,
                max_tokens=args.max_tokens,
                max_workers=args.max_workers,
            )
        )

    if summaries:
        print("\n" + "=" * 60)
        print("All datasets summary")
        print("=" * 60)
        for s in summaries:
            print(
                f"  {s['dataset']:10s} "
                f"acc={100 * s['accuracy']:6.2f}% "
                f"({s['correct']}/{s['total']})  "
                f"offload_rate={100 * s['offload_rate']:5.1f}% "
                f"({s['offload_count']}/{s['total']})"
            )
        print("=" * 60)


if __name__ == "__main__":
    main()
