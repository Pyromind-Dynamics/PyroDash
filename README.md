# pyroDash

**Language / 语言:** bilingual EN + 中文（this file） · 本文件为中英对照

<a href="https://PyroMind-Dynamics.github.io/pyroDash/"><img src="https://img.shields.io/badge/🌐%20Website-GitHub%20Pages-blue"/></a>&nbsp;&nbsp;<a href="https://arxiv.org/abs/2607.20327"><img src="https://img.shields.io/badge/📄%20Paper-arXiv-red"/></a>&nbsp;&nbsp;<a href="https://huggingface.co/pyromind"><img src="https://img.shields.io/badge/🤗%20HuggingFace-pyromind-yellow"/></a>

---

## 🔥 Updates / 更新

- **2026-07-23**: Paper on [arXiv:2607.20327](https://arxiv.org/abs/2607.20327).  
  **2026-07-23**：论文发布于 [arXiv:2607.20327](https://arxiv.org/abs/2607.20327)。

- **2026-07-22**: Release project page, math evaluation code, [EasyHard-24K](https://huggingface.co/datasets/pyromind/easyhard-24k), and models on [Hugging Face · pyromind](https://huggingface.co/pyromind) ([SFT](https://huggingface.co/pyromind/PyroDash-4B-SFT), [GRPO λ=0.05](https://huggingface.co/pyromind/PyroDash-4B-GRPO-Lambda-0.05), [GRPO λ=0.6](https://huggingface.co/pyromind/PyroDash-4B-GRPO-Lambda-0.6)). Milestone 1 math eval loop largely done; Collaborate Engine & one-click reproduce still in progress.  
  **2026-07-22**：发布项目主页、数学评测代码、[EasyHard-24K](https://huggingface.co/datasets/pyromind/easyhard-24k)，以及模型（见 [Hugging Face · pyromind](https://huggingface.co/pyromind)）。Milestone 1 数学评测闭环基本完成；Collaborate Engine 与一键复现仍在进行中。

## 📊 Results / 结果

| Agentic-Preview                                                                              | Math                                                                       |
| -------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| ![Cost–Accuracy Pareto (Agentic-Preview)](./docs/assets/fig_cost_accuracy_pareto_coding.png) | ![Cost–Accuracy Pareto (Math)](./docs/assets/fig_cost_accuracy_pareto.png) |

> [!IMPORTANT]
> **Agentic-Preview changes / Agentic-Preview 更新**
>
> - Control token upgraded from `<|llm_offload|>` to `<|llm_offload|>N<|/llm_offload|>`, where N is an integer in 0–9 that selects the thinking level when handing off to a more capable model.  
>   控制符由 `<|llm_offload|>` 升级为 `<|llm_offload|>N<|/llm_offload|>`，N 为 0–9，用于选择 thinking level。
> - Stage 2 training updated from offload SFT alone to **SFT + OPD**.  
>   第二阶段由单独 offload SFT 升级为 **SFT + OPD**。
> - Agentic coding training datasets: **ScaleSWE**, **TMax**.  
>   Agentic coding 训练数据：**ScaleSWE**、**TMax**。
> - Evaluation: see [`evaluation/evaluation_code/swe-bench/README.md`](evaluation/evaluation_code/swe-bench/README.md)  
>   评测见该 README。
> - More details will be released later. / 更多细节后续发布。

---

<table>
<tr>
<td width="50%" valign="top">
<img src="./docs/assets/inference.png" alt="Inference Architecture" width="100%"/>
</td>
<td width="50%" valign="middle" style="padding: 0 2em;">

&emsp;&emsp;We propose **PyroDash**, a token-level dynamic reasoning paradigm for collaborative inference between small and large language models. PyroDash enables the small model to autonomously emit the control token `<|llm_offload|>` during autoregressive streaming decoding; the collaboration engine then dynamically offloads the local reasoning chain to a large model based on this control signal. This approach requires neither an additional router model nor retraining of the large model, and is naturally compatible with closed-source LLM services.

&emsp;&emsp;我们提出 **PyroDash**，一种面向小模型与大模型协同推理的 Token 级动态推理范式。小模型在自回归流式解码中自行输出控制符 `<|llm_offload|>`，协同引擎据此将局部推理链转交大模型补全。无需外接 Router，亦无需重训练大模型，并兼容闭源大模型服务。

</td>
</tr>
</table>

During training, PyroDash follows a three-stage progressive optimization pipeline: (1) train the control-token embedding layer so the small model acquires basic offloading expressiveness; (2) cold-start the offload capability to establish a collaboration pattern between the small and large models; and (3) apply GRPO reinforcement learning that jointly optimizes the dynamic offloading policy with a task-accuracy reward and a large-model call-cost penalty, achieving an adaptive balance between reasoning quality and compute cost. For more details, please refer to our paper (citation below).

训练上，PyroDash 采用三阶段渐进式优化：（1）训练控制符嵌入层，使小模型具备基本 offload 表达能力；（2）冷启动 offload，建立大小模型协作模式；（3）以 GRPO 联合优化动态 offload 策略，结合任务准确率奖励与大模型调用成本惩罚，在推理质量与算力成本之间取得自适应平衡。更多细节见下方论文引用。

<p align="center">
  <img src="./docs/assets/training.png" alt="Three-stage progressive training pipeline" width="80%"/>
</p>

---

## 🚀 Quick Start / 快速开始

### 1. Setup / 环境准备

```bash
git clone https://github.com/PyroMind-Dynamics/pyroDash.git
cd pyroDash
# Shared / SLM serving · 公共 / SLM serving
pip install -r requirements.txt
# Then install the task folder you need · 按任务再装对应目录，e.g.:
#   pip install -r evaluation/evaluation_math/requirements.txt
#   pip install -r evaluation/evaluation_code/swe-bench/requirements.txt
```

### 2. Math offload + evaluation / 数学 Offload + 评测

Start the math adapter (local vLLM on `8001` + adapter on `18031`), then run the thin eval client.  
先起数学 adapter（本地 vLLM `8001` + adapter `18031`），再跑评测客户端：

```bash
# Terminal 1 — adapter (edit MODEL_PATH / LLM_*):
MODEL_PATH=/path/to/your/merged_model \
LLM_BASE_URL=http://your-llm-host/v1 LLM_API_KEY=... LLM_MODEL=... \
  bash offload/offload_math/api.sh

# Terminal 2 — benchmarks:
bash evaluation/evaluation_math/math_eval.sh
```

- Adapter: [`offload/offload_math/README.md`](offload/offload_math/README.md) — SLM `/completions` + bare `<|llm_offload|>` + LLM relay; `POST /v1/math/complete`  
  Adapter：小模型 `/completions` + 裸 `<|llm_offload|>` + 大模型 relay
- Eval client: [`evaluation/evaluation_math/README.md`](evaluation/evaluation_math/README.md) — datasets, `\boxed{}` scoring, JSON  
  评测客户端：数据集、`\boxed{}` 判分、JSON

Tokenizer must include the special token `<|llm_offload|>`.  
Tokenizer 必须包含特殊 token `<|llm_offload|>`。

### 3. Code offload API / Code Offload API（`offload/offload_code`）

Standalone SLM+LLM adapter (tag or entropy). Start the API, then point any client at `api_base`.  
独立的 SLM+LLM adapter（tag / entropy）。先起 API，再让客户端把 `api_base` 指过去：

```bash
# edit MODEL_PATH / LLM_* / ports in the config block, then:
bash offload/offload_code/tag/api.sh
# or: bash offload/offload_code/entropy/api.sh
```

See [`offload/offload_code/README.md`](offload/offload_code/README.md). SWE-bench client: [`evaluation/evaluation_code/swe-bench/README.md`](evaluation/evaluation_code/swe-bench/README.md).  
详见上述 README。

---

## 📊 Results / 结果图

<p align="center">
  <img src="./docs/assets/fig_cost_accuracy_pareto.png" alt="Cost–Accuracy Pareto" width="70%"/>
</p>

---

## 📋 TODO

**Milestone 1 — Math eval loop / Math 场景评测闭环**

- [x] Baselines: GLM-5.2 upper / Qwen3.5-4B lower + token cost · 基线 + Token 成本
- [x] vLLM + GLM relay (`<|llm_offload|>`) + per-dataset JSON + cost aggregation
- [x] Comparisons: PyroDash / Query Router / Token Router + Pareto · 对比与帕累托曲线
- [x] λ sweep & ablations · λ 扫描与消融
- [ ] One-click reproduce on [PyroMind Console](https://pyromind.ai/) · 一键复现
- [ ] Collaborate Engine

**Milestone 2 — Coding + Agentic**

- [ ] SWE-Bench (Verified / Lite) harness
- [ ] Terminal-Bench v2 harness
- [ ] Sandbox / scoring + offload trajectory & token stats · Sandbox / 判分 + 轨迹与 Token 统计
- [ ] Qwen3.5-4B / GLM-5.2 / PyroDash comparison + cost tables
- [ ] Unified Math + SWE + Terminal results & end-to-end scripts · 统一结果表与端到端脚本

**Milestone 3 — Coding Plan release / 发布 Coding Plan**

- [ ] Product definition & collaborative inference integration · 产品定义与协同推理集成
- [ ] Coding-scenario optimizations (completion / refactor / debug) · 编程场景专项优化
- [ ] Release & promotion · 发布与推广

---

## 🔗 Resources / 相关资源

| Resource / 资源 | Link / 链接 |
|-----------------|-------------|
| Project website / 项目官网 | [PyroMind-Dynamics.github.io/pyroDash](https://PyroMind-Dynamics.github.io/pyroDash/) |
| Paper / 论文 | [arXiv:2607.20327](https://arxiv.org/abs/2607.20327) |
| Dataset (EasyHard-24K) / 数据集 | [huggingface.co/datasets/pyromind/easyhard-24k](https://huggingface.co/datasets/pyromind/easyhard-24k) |
| Hugging Face org / 组织 | [huggingface.co/pyromind](https://huggingface.co/pyromind) |

---

## 📖 Citation / 引用

If you find PyroDash useful, please cite:  
如果本工作对你有帮助，请引用：

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

Dataset / 数据集：

```bibtex
@misc{pyromind2026easyhard24k,
  title        = {{EasyHard-24K} v0.02},
  author       = {{PyroMind Dynamics}},
  year         = {2026},
  howpublished = {\url{https://huggingface.co/datasets/pyromind/easyhard-24k}}
}
```
