"""Offload benchmark: local small vLLM serve -> GLM relay -> score. Thinking always on."""

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
from llm_relay import OFFLOAD_TAG, complete_offload_batch  # noqa: E402

SMALL_MAX_WORKERS = 256
TEMPERATURE = 0.1

OFFLOAD_TOKEN = OFFLOAD_TAG
SYSTEM_PROMPT = (
    "You are a helpful assistant. Solve the given problem step by step. "
    "For very difficult steps, you can output <|llm_offload|> to request help "
    "from a more capable model."
)
PROMPT_SUFFIX = (
    "\nPlease reason step by step, and put your final answer within \\boxed{}."
)


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


def build_chat_messages(question: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question + PROMPT_SUFFIX},
    ]


def format_prompt(tokenizer, question: str) -> str:
    """Same prompt formatting as the old in-process vLLM path."""
    messages = build_chat_messages(question)
    kwargs = {"tokenize": False, "add_generation_prompt": True}
    try:
        return tokenizer.apply_chat_template(messages, enable_thinking=True, **kwargs)
    except TypeError:
        return tokenizer.apply_chat_template(messages, **kwargs)


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


def call_small_completion(
    prompt: str, *, small_base_url: str, small_model: str, max_tokens: int
) -> tuple[str, dict[str, int]]:
    """Call /v1/completions so stop string + full text match training/eval behavior."""
    url = f"{small_base_url.rstrip('/')}/completions"
    body = {
        "model": small_model,
        "prompt": prompt,
        "temperature": TEMPERATURE,
        "max_tokens": max_tokens,
        "stop": [OFFLOAD_TOKEN],
        "include_stop_str_in_output": True,
        "skip_special_tokens": False,
    }
    resp = requests.post(url, json=body, timeout=600.0)
    resp.raise_for_status()
    data = resp.json()
    choice = data["choices"][0]
    text = str(choice.get("text") or "")
    stop_reason = choice.get("stop_reason")
    # safety: keep tag even if server omits it
    if OFFLOAD_TOKEN not in text and (
        stop_reason == OFFLOAD_TOKEN
        or (isinstance(stop_reason, str) and OFFLOAD_TOKEN in stop_reason)
    ):
        text = text + OFFLOAD_TOKEN
    usage = normalize_usage(data.get("usage")) or {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    }
    return text, usage


def run_small_batch(
    questions: list[str],
    *,
    tokenizer,
    small_base_url: str,
    small_model: str,
    max_tokens: int,
) -> tuple[list[str], list[list[int]], list[dict[str, int]]]:
    prompts = [format_prompt(tokenizer, q) for q in questions]
    raw_responses = [""] * len(questions)
    usages: list[dict[str, int]] = [
        {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0} for _ in questions
    ]
    completion_ids: list[list[int]] = [[] for _ in questions]

    def _run(idx: int) -> tuple[int, str, dict[str, int]]:
        text, usage = call_small_completion(
            prompts[idx],
            small_base_url=small_base_url,
            small_model=small_model,
            max_tokens=max_tokens,
        )
        return idx, text, usage

    workers = max(1, min(SMALL_MAX_WORKERS, len(questions)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_run, i) for i in range(len(questions))]
        for fut in tqdm(
            as_completed(futures),
            total=len(questions),
            desc="[small] generate",
            unit="sample",
        ):
            idx, text, usage = fut.result()
            raw_responses[idx] = text
            usages[idx] = usage
            completion_ids[idx] = [0] * int(usage.get("completion_tokens", 0))

    return raw_responses, completion_ids, usages


def relay_with_glm(
    raw_responses,
    questions,
    *,
    api_key,
    completion_ids,
    glm_base_url: str,
    glm_model: str,
    glm_max_workers: int,
    max_tokens: int,
):
    prompts = [build_chat_messages(q) for q in questions]
    n_off = sum(OFFLOAD_TOKEN in r for r in raw_responses)
    print(f"[glm] relay {n_off}/{len(raw_responses)} via {glm_model} @ {glm_base_url}")
    return complete_offload_batch(
        raw_responses,
        prompts,
        api_key=api_key,
        base_url=glm_base_url,
        model=glm_model,
        max_tokens=max_tokens,
        max_workers=glm_max_workers,
        completion_ids=completion_ids,
        enable_thinking=True,
    )


def build_records(
    questions,
    answers,
    raw_responses,
    completed_responses,
    small_usages,
    glm_usages,
) -> list[SampleRecord]:
    records = []
    for idx, (question, answer, raw, completed) in enumerate(
        zip(questions, answers, raw_responses, completed_responses)
    ):
        qwen_usage = small_usages[idx] if idx < len(small_usages) else {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
        }
        records.append(
            SampleRecord(
                idx=idx,
                question=question,
                answer=answer,
                raw_response=raw,
                completed_response=completed,
                has_offload=OFFLOAD_TOKEN in raw,
                score=1 if boxed_socre.compare_answer(completed, answer) else 0,
                qwen_usage=qwen_usage,
                glm_usage=normalize_usage(glm_usages[idx] if idx < len(glm_usages) else None),
            )
        )
    return records


def summarize_records(dataset, records, wall_s) -> dict[str, Any]:
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
        "total_glm_completion_tokens": sum((r.glm_usage or {}).get("completion_tokens", 0) for r in records),
        "wall_s": wall_s,
        "correct": len(correct),
    }


def print_summary(summary: dict[str, Any]) -> None:
    print("=" * 60)
    print(f"  Dataset:     {summary['dataset']}")
    print(f"  Accuracy:    {100 * summary['accuracy']:.2f}% ({summary['correct']}/{summary['total']})")
    print(f"  Offload:     {summary['offload_count']}/{summary['total']} ({100 * summary['offload_rate']:.1f}%)")
    print("=" * 60)


def run_dataset(
    dataset_name: str,
    output_dir: Path,
    *,
    tokenizer,
    small_base_url: str,
    small_model: str,
    api_key: str,
    glm_base_url: str,
    glm_model: str,
    glm_max_workers: int,
    max_tokens: int,
) -> dict[str, Any]:
    result_path = output_dir / f"{dataset_name}_results.json"
    handler = datasets_loader.get_dataset_handler(dataset_name)
    questions, answers = handler.load_data()

    t0 = time.perf_counter()
    raw_responses, completion_ids, small_usages = run_small_batch(
        questions,
        tokenizer=tokenizer,
        small_base_url=small_base_url,
        small_model=small_model,
        max_tokens=max_tokens,
    )

    completed = list(raw_responses)
    glm_usages: list[dict[str, Any] | None] = [None] * len(raw_responses)
    pending = [i for i, r in enumerate(raw_responses) if OFFLOAD_TOKEN in r]

    if pending:
        print(f"[glm] relay {len(pending)}/{len(raw_responses)} samples")
        sub_done, sub_usage = relay_with_glm(
            [raw_responses[i] for i in pending],
            [questions[i] for i in pending],
            api_key=api_key,
            completion_ids=[completion_ids[i] for i in pending],
            glm_base_url=glm_base_url,
            glm_model=glm_model,
            glm_max_workers=glm_max_workers,
            max_tokens=max_tokens,
        )
        for j, idx in enumerate(pending):
            completed[idx] = sub_done[j]
            glm_usages[idx] = sub_usage[j]

    records = build_records(
        questions, answers, raw_responses, completed, small_usages, glm_usages,
    )
    summary = summarize_records(dataset_name, records, time.perf_counter() - t0)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    with result_path.open("w", encoding="utf-8") as f:
        json.dump({"summary": summary, "samples": [asdict(r) for r in records]}, f, ensure_ascii=False, indent=2)
    print_summary(summary)
    print(f"[save] {result_path}")
    return summary


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--model-path",
        required=True,
        help="local merged model dir (for tokenizer / chat template)",
    )
    p.add_argument("--small-base-url", required=True)
    p.add_argument("--small-model", required=True)
    p.add_argument("--output-dir", default="./results")
    p.add_argument(
        "--datasets",
        nargs="+",
        default=["math", "gsm8k", "minerva", "olympiad", "aime2024", "aime2025"],
    )
    p.add_argument("--glm-base-url", required=True)
    p.add_argument("--glm-api-key", required=True)
    p.add_argument("--glm-model", required=True)
    p.add_argument("--glm-max-workers", type=int, default=256)
    p.add_argument(
        "--max-tokens",
        type=int,
        default=8192,
        help="small max_tokens; also total completion budget for small+glm",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    from transformers import AutoTokenizer

    model_path = Path(args.model_path).resolve()
    tokenizer = AutoTokenizer.from_pretrained(str(model_path), trust_remote_code=True)
    if OFFLOAD_TOKEN not in tokenizer.get_vocab():
        raise RuntimeError(f"Tokenizer missing {OFFLOAD_TOKEN!r}")

    print(f"[config] model_path={model_path}")
    print(f"[config] small={args.small_base_url} model={args.small_model}")
    print(f"[config] glm={args.glm_base_url} model={args.glm_model}")
    print(f"[config] max_tokens={args.max_tokens} (small + glm budget)")
    print(f"[config] output_dir={output_dir}")
    print(f"[config] datasets={args.datasets}")

    summaries = []
    for name in args.datasets:
        print(f"\n>>> {name}")
        summaries.append(
            run_dataset(
                name,
                output_dir,
                tokenizer=tokenizer,
                small_base_url=args.small_base_url,
                small_model=args.small_model,
                api_key=args.glm_api_key,
                glm_base_url=args.glm_base_url,
                glm_model=args.glm_model,
                glm_max_workers=args.glm_max_workers,
                max_tokens=args.max_tokens,
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
