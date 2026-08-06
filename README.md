# PyroDash

**Language / 语言:** [English](README.md) | [中文](README_zh.md)

<a href="https://PyroMind-Dynamics.github.io/PyroDash/"><img src="https://img.shields.io/badge/🌐%20Website-GitHub%20Pages-blue"/></a>&nbsp;&nbsp;<a href="https://arxiv.org/abs/2607.20327"><img src="https://img.shields.io/badge/📄%20Paper-arXiv-red"/></a>&nbsp;&nbsp;<a href="https://huggingface.co/pyromind"><img src="https://img.shields.io/badge/🤗%20HuggingFace-pyromind-yellow"/></a>

---

## 🔥 Updates

- **2026-07-23**: Paper on [arXiv:2607.20327](https://arxiv.org/abs/2607.20327).
- **2026-07-22**: Release project page, math evaluation code, [EasyHard-24K](https://huggingface.co/datasets/pyromind/easyhard-24k), and models on [Hugging Face · pyromind](https://huggingface.co/pyromind) ([SFT](https://huggingface.co/pyromind/PyroDash-4B-SFT), [GRPO λ=0.05](https://huggingface.co/pyromind/PyroDash-4B-GRPO-Lambda-0.05), [GRPO λ=0.6](https://huggingface.co/pyromind/PyroDash-4B-GRPO-Lambda-0.6)). Milestone 1 math eval loop largely done; Collaborate Engine & one-click reproduce still in progress.

---

<table>
<tr>
<td width="50%" valign="top">
<img src="./docs/assets/inference.png" alt="Inference Architecture" width="100%"/>
</td>
<td width="50%" valign="middle" style="padding: 0 2em;">

&emsp;&emsp;We propose **PyroDash**, a token-level dynamic reasoning paradigm for collaborative inference between small and large language models. PyroDash enables the small model to autonomously emit the control token `<|llm_offload|>` during autoregressive streaming decoding; the collaboration engine then dynamically offloads the local reasoning chain to a large model based on this control signal. This approach requires neither an additional router model nor retraining of the large model, and is naturally compatible with closed-source LLM services.

</td>
</tr>
</table>

During training, PyroDash follows a three-stage progressive optimization pipeline: (1) train the control-token embedding layer so the small model acquires basic offloading expressiveness; (2) cold-start the offload capability to establish a collaboration pattern between the small and large models; and (3) apply GRPO reinforcement learning that jointly optimizes the dynamic offloading policy with a task-accuracy reward and a large-model call-cost penalty, achieving an adaptive balance between reasoning quality and compute cost. For more details, please refer to our paper (citation below).

<p align="center">
  <img src="./docs/assets/training.png" alt="Three-stage progressive training pipeline" width="80%"/>
</p>

---

## 🚀 Quick Start

### 1. Setup

```bash
git clone https://github.com/PyroMind-Dynamics/PyroDash.git
cd PyroDash
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
  <img src="./docs/assets/fig_cost_accuracy_pareto.png" alt="Cost–Accuracy Pareto" width="70%"/>
</p>

---

## 📋 TODO

**Milestone 1 — Math eval loop**

- [x] Baselines: GLM-5.2 upper bound / Qwen3.5-4B lower bound + token cost stats
- [x] vLLM + GLM relay (`<|llm_offload|>`) + per-dataset JSON + cost aggregation
- [x] Comparisons: PyroDash / Query Router / Token Router + Pareto curve
- [x] λ sweep & ablations
- [ ] One-click reproduce on [PyroMind Console](https://pyromind.ai/) (end-to-end eval)
- [ ] Collaborate Engine

**Milestone 2 — Coding + Agentic**

- [ ] SWE-Bench (Verified / Lite) harness
- [ ] Terminal-Bench v2 harness
- [ ] Sandbox / scoring + offload trajectory & token stats
- [ ] Qwen3.5-4B / GLM-5.2 / PyroDash comparison + cost tables
- [ ] Unified Math + SWE + Terminal results & end-to-end scripts

**Milestone 3 — Coding Plan release**

- [ ] Product definition & collaborative inference integration
- [ ] Coding-scenario optimizations (completion / refactor / debug)
- [ ] Release & promotion

---

## 🔗 Resources

| Resource | Link |
|----------|------|
| Project website | [PyroMind-Dynamics.github.io/PyroDash](https://PyroMind-Dynamics.github.io/PyroDash/) |
| Paper | [arXiv:2607.20327](https://arxiv.org/abs/2607.20327) |
| Dataset (EasyHard-24K) | [huggingface.co/datasets/pyromind/easyhard-24k](https://huggingface.co/datasets/pyromind/easyhard-24k) |
| Hugging Face org | [huggingface.co/pyromind](https://huggingface.co/pyromind) |

---

## 📖 Citation

If you find PyroDash useful, please cite:

```bibtex
@misc{lyu2026pyrodash,
  title        = {PyroDash: Cost-Efficient Token-Level Small-Large Language Model Collaborative Inference},
  author       = {Niqi Lyu and Pengtao Shi and Wei Qiu and Jianlin Zhong and Sicong Xia and Jianyao Ma and Yicheng Ding},
  year         = {2026},
  eprint       = {2607.20327},
  archivePrefix= {arXiv},
  primaryClass = {cs.CL},
  url          = {https://arxiv.org/abs/2607.20327}
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
