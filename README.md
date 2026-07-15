# pyroDash-evaluate

**Language / 语言:** [English](README.md) | [中文](README_zh.md)

<p align="center">
  <!-- TODO: replace links below -->
  <a href="TODO_MODEL_URL"><img src="https://img.shields.io/badge/🤗%20Model-Coming%20Soon-yellow" alt="Model"></a>
  <a href="TODO_REPRODUCE_URL"><img src="https://img.shields.io/badge/🚀%20Quick%20Reproduce-PyroMind-orange" alt="Quick Reproduce"></a>
  <a href="TODO_PAPER_URL"><img src="https://img.shields.io/badge/📄%20Paper-Coming%20Soon-lightgrey" alt="Paper"></a>
</p>

> **Quick reproduce:** Click [🚀 Quick Reproduce](TODO_REPRODUCE_URL) to open our company platform and reproduce the evaluation end-to-end with one click.

---

## Overview

![Cost–Accuracy Pareto](./figs/fig_cost_accuracy_pareto.png)

![Inference Architecture](./figs/fig_inference_architecture.png)

---

## Quick Start

### 1. Setup

```bash
git clone https://github.com/PyroMind-Dynamics/pyroDash-evaluate.git
cd pyroDash-evaluate
pip install -r requirements.txt
```

### 2. Run evaluation (`evaluation/math_eval.sh`)

Edit placeholders in [`evaluation/math_eval.sh`](evaluation/math_eval.sh), then:

```bash
bash evaluation/math_eval.sh
```

The script (1) starts a local **vLLM** server for the small model on port `8001`, (2) runs `math_eval.py`, and (3) stops vLLM on exit.

#### Must set

| Variable / flag | Meaning | Example |
|-----------------|---------|---------|
| `MODEL` | Local merged model path (vLLM serve + tokenizer) | `/path/to/your/merged_model` |
| `--glm-base-url` | OpenAI-compatible API for the large/relay model | `http://your-glm-host:8000/v1` |
| `--glm-api-key` | API key for that endpoint | `your-glm-api-key` |
| `--glm-model` | Served model name on the GLM side | `your-glm-model` |

#### Common options

| Flag | Meaning | Typical value |
|------|---------|---------------|
| `--model-path` | Same as `MODEL` (tokenizer / chat template) | `"$MODEL"` |
| `--small-base-url` | Local vLLM OpenAI API root | `http://127.0.0.1:8001/v1` |
| `--small-model` | Local served model name | `small-model` |
| `--output-dir` | Per-dataset JSON output directory | `./results_500` |
| `--datasets` | Benchmarks (space-separated) | `gsm8k minerva olympiad aime2024 aime2025` |
| `--max-tokens` | Small-model max tokens; also total small+GLM budget | `8192` |

#### vLLM settings in the script

| Setting | Meaning |
|---------|---------|
| `CUDA_VISIBLE_DEVICES` | GPU id |
| `--port 8001` | Local serve port (keep in sync with `--small-base-url`) |
| `--served-model-name small-model` | Keep in sync with `--small-model` |
| `--max-model-len` | Context length |
| `--gpu-memory-utilization` | GPU memory fraction |

Tokenizer must include the special token `<|llm_offload|>`.

---

## Results



---

## Citation


