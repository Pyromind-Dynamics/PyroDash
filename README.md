# pyroDash

**Language / 语言:** [English](README.md) | [中文](README_zh.md)

<a href="https://PyroMind-Dynamics.github.io/pyroDash-evaluate/"><img src="https://img.shields.io/badge/🌐%20Website-GitHub%20Pages-blue"/></a>&nbsp;&nbsp;<a href="#-citation"><img src="https://img.shields.io/badge/📄%20Paper-Preprint-blue"/></a>&nbsp;&nbsp;<a href="https://huggingface.co/datasets/pyromind/easyhard-24k"><img src="https://img.shields.io/badge/🤗%20Dataset-EasyHard--24K-yellow"/></a>&nbsp;&nbsp;<a href="https://huggingface.co/pyromind"><img src="https://img.shields.io/badge/🤗%20HuggingFace-pyromind-yellow"/></a>&nbsp;&nbsp;<a href="https://pyromind.ai/"><img src="https://img.shields.io/badge/🚀%20Quick%20Reproduce-PyroMind-orange"/></a>

---

> **Quick reproduce:** Open [PyroMind Console](https://pyromind.ai/) to reproduce the evaluation end-to-end with one click. Training data: [EasyHard-24K](https://huggingface.co/datasets/pyromind/easyhard-24k) on Hugging Face.

<table>
<tr>
<td width="50%" valign="top">
<img src="./figs/fig_inference_architecture.png" alt="Inference Architecture" width="100%"/>
</td>
<td width="50%" valign="top">

We propose **PyroDash**, a token-level dynamic reasoning paradigm for collaborative inference between small and large language models. PyroDash enables the small model to autonomously emit the control token `<|llm_offload|>` during autoregressive streaming decoding; the collaboration engine then dynamically offloads the local reasoning chain to a large model based on this control signal. This approach requires neither an additional router model nor retraining of the large model, and is naturally compatible with closed-source LLM services.

</td>
</tr>
</table>

During training, PyroDash follows a three-stage progressive optimization pipeline: (1) train the control-token embedding layer so the small model acquires basic offloading expressiveness; (2) cold-start the offload capability to establish a collaboration pattern between the small and large models; and (3) apply GRPO reinforcement learning that jointly optimizes the dynamic offloading policy with a task-accuracy reward and a large-model call-cost penalty, achieving an adaptive balance between reasoning quality and compute cost. For more details, please refer to our paper (citation below).

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

## 🔗 Resources

| Resource | Link |
|----------|------|
| Project website | [PyroMind-Dynamics.github.io/pyroDash-evaluate](https://PyroMind-Dynamics.github.io/pyroDash-evaluate/) |
| Paper | Preprint — see [Citation](#-citation) |
| Dataset (EasyHard-24K) | [huggingface.co/datasets/pyromind/easyhard-24k](https://huggingface.co/datasets/pyromind/easyhard-24k) |
| Hugging Face org | [huggingface.co/pyromind](https://huggingface.co/pyromind) |
| PyroMind Console | [pyromind.ai](https://pyromind.ai/) |

---

## 📖 Citation

If you find PyroDash useful, please cite:

```bibtex
@misc{pyrodash2026,
  title        = {PyroDash: Cost-Efficient Token-Level Small-Large Model Collaborative Inference},
  author       = {{PyroMind Dynamics}},
  year         = {2026},
  note         = {Preprint}
}
```

Dataset:

```bibtex
@misc{pyromind2026easyhard24k,
  title        = {{EasyHard-24K} v0.02},
  author       = {{PyroMind Dynamics}},
  year         = {2026},
  howpublished = {\url{https://huggingface.co/datasets/pyromind/easyhard-24k}}
}
```
