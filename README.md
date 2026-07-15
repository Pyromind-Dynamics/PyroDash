# pyroDash

**Language / 语言:** [English](README.md) | [中文](README_zh.md)

<a href="TODO_PAPER_URL"><img src="https://img.shields.io/badge/📄%20Paper-Coming%20Soon-lightgrey"/></a>&nbsp;&nbsp;<a href="TODO_MODEL_URL"><img src="https://img.shields.io/badge/🤗%20Model-Coming%20Soon-yellow"/></a>&nbsp;&nbsp;<a href="TODO_REPRODUCE_URL"><img src="https://img.shields.io/badge/🚀%20Quick%20Reproduce-PyroMind-orange"/></a>

---

> **Quick reproduce:** Click [🚀 Quick Reproduce](TODO_REPRODUCE_URL) to open our company platform and reproduce the evaluation end-to-end with one click.

<table>
<tr>
<td width="50%" valign="top">
<img src="./figs/fig_inference_architecture.png" alt="Inference Architecture" width="100%"/>
</td>
<td width="50%" valign="top">

</td>
</tr>
</table>

---

## 🚀 Quick Start

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

#### Parameters

| Variable / flag | Meaning | Example |
|-----------------|---------|---------|
| `MODEL` | Local merged model path (vLLM serve + tokenizer) | `/path/to/your/merged_model` |
| `--glm-base-url` | OpenAI-compatible API for the large/relay model | `http://your-glm-host:8000/v1` |
| `--glm-api-key` | API key for that endpoint | `your-glm-api-key` |
| `--glm-model` | Served model name on the GLM side | `your-glm-model` |
| `--output-dir` | Per-dataset JSON output directory | `./results_500` |
| `--datasets` | Benchmarks (space-separated) | `gsm8k minerva olympiad aime2024 aime2025` |

Tokenizer must include the special token `<|llm_offload|>`.

---

## 📊 Results

<p align="center">
  <img src="./figs/fig_cost_accuracy_pareto.png" alt="Cost–Accuracy Pareto" width="70%"/>
</p>

---

## 📖 Citation

