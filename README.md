# pyroDash-eval

**Language / 语言:** [English](README.md) | [中文](README_zh.md)

Offload math evaluation: local small model (vLLM) generates first; if it emits `<|llm_offload|>`, a stronger GLM continues; answers are scored via `\boxed{}`.

## Layout

| File | Role |
|------|------|
| `math_eval.sh` | Start vLLM, then run evaluation |
| `math_eval.py` | Main eval loop: prompt → small model → optional GLM relay → score → save JSON |
| `datasets_loader.py` | Load benchmark questions/answers (`get_dataset_handler`) |
| `boxed_socre.py` | Score `\boxed{}` answers (`compare_answer`, `score_boxed_answer`, …) |
| `llm_relay.py` | Relay offloaded samples to GLM (`complete_offload_batch`) |

### Key functions

- **`datasets_loader.get_dataset_handler(name)`** — return a handler; call `load_data()` → `(questions, answers)`.
- **`boxed_socre.compare_answer(response, answer)`** — True if predicted `\boxed{}` matches ground truth (via `math_verify`).
- **`llm_relay.complete_offload_batch(...)`** — for responses containing `<|llm_offload|>`, continue generation with GLM.
- **`math_eval.run_dataset(...)`** — run one dataset end-to-end and write `{dataset}_results.json`.

## Quick start

1. Edit placeholders in `math_eval.sh` (see below).
2. Install deps: `pip install math_verify mathruler pylatexenc requests tqdm pandas datasets transformers` (plus `vllm` on the GPU machine).
3. Run:

```bash
bash math_eval.sh
```

Results land under `--output-dir` (default in the script: `./results_500`).

---

## `math_eval.sh` — what to set

Script flow: (1) `vllm serve` the small model on port `8001`; (2) call `math_eval.py` with the same model + GLM relay settings.

### Must change (placeholders)

| Variable / flag | Meaning | What to pass |
|-----------------|---------|--------------|
| `MODEL` | Local merged model directory used by both `vllm serve` and tokenizer loading | Absolute path to your checkpoint, e.g. `/path/to/your/merged_model` |
| `--glm-base-url` | OpenAI-compatible API base for the large/relay model | e.g. `http://your-glm-host:8000/v1` |
| `--glm-api-key` | API key for that endpoint | e.g. `your-glm-api-key` (or whatever the server expects) |
| `--glm-model` | Served model name on the GLM side | e.g. `your-glm-model` (must match the remote `--served-model-name`) |

### Usually keep / tune as needed

| Flag | Meaning | Typical value |
|------|---------|---------------|
| `--model-path` | Same as `MODEL`; used only to load tokenizer / chat template | `"$MODEL"` |
| `--small-base-url` | Local vLLM OpenAI API root | `http://127.0.0.1:8001/v1` (must match serve host/port) |
| `--small-model` | Local served model name | `small-model` (must match `--served-model-name` in `vllm serve`) |
| `--output-dir` | Where per-dataset JSON results go | e.g. `./results_500` |
| `--datasets` | Benchmarks to run (space-separated) | one or more of: `math` `gsm8k` `minerva` `olympiad` `aime2024` `aime2025` `amc` `mydataset` |
| `--max-tokens` | Max completion tokens for the small model; also the **total** small+GLM completion budget | e.g. `8192` |
| `--glm-max-workers` | Parallel GLM requests (set in Python CLI; not in the default `.sh`) | default `256` |

### vLLM block in the script

| Setting | Meaning |
|---------|---------|
| `CUDA_VISIBLE_DEVICES` | Which GPU to use |
| `--port 8001` | Local serve port (keep in sync with `--small-base-url`) |
| `--served-model-name small-model` | Name clients use; keep in sync with `--small-model` |
| `--max-model-len` | Context length for vLLM |
| `--gpu-memory-utilization` | GPU memory fraction |

---

## Example after filling in

```bash
MODEL=/data/models/offload_merged_ckpt

python math_eval.py \
  --model-path "$MODEL" \
  --small-base-url http://127.0.0.1:8001/v1 \
  --small-model small-model \
  --output-dir ./results \
  --datasets math gsm8k \
  --glm-base-url http://127.0.0.1:8000/v1 \
  --glm-api-key sk-xxx \
  --glm-model glm-fp8 \
  --max-tokens 8192
```

Tokenizer must include the special token `<|llm_offload|>`; otherwise `math_eval.py` exits with an error.
