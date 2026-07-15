# pyroDash-evaluate

**Language / 语言:** [English](README.md) | [中文](README_zh.md)

<p align="center">
  <!-- TODO: 替换下方链接 -->
  <a href="TODO_MODEL_URL"><img src="https://img.shields.io/badge/🤗%20Model-Coming%20Soon-yellow" alt="Model"></a>
  <a href="TODO_REPRODUCE_URL"><img src="https://img.shields.io/badge/🚀%20Quick%20Reproduce-PyroMind-orange" alt="Quick Reproduce"></a>
  <a href="TODO_PAPER_URL"><img src="https://img.shields.io/badge/📄%20Paper-Coming%20Soon-lightgrey" alt="Paper"></a>
</p>

> **一键复现：** 点击 [🚀 Quick Reproduce](TODO_REPRODUCE_URL)，进入公司平台即可端到端快速复现评测。

---

## Overview

![Cost–Accuracy Pareto](./figs/fig_cost_accuracy_pareto.png)

![Inference Architecture](./figs/fig_inference_architecture.png)

---

## 快速开始

### 1. 环境准备

```bash
git clone https://github.com/PyroMind-Dynamics/pyroDash-evaluate.git
cd pyroDash-evaluate
pip install -r requirements.txt
```

### 2. 运行评测（`evaluation/math_eval.sh`）

先修改 [`evaluation/math_eval.sh`](evaluation/math_eval.sh) 中的占位参数，再执行：

```bash
bash evaluation/math_eval.sh
```

脚本流程：(1) 在本地 `8001` 端口用 **vLLM** 拉起小模型；(2) 运行 `math_eval.py`；(3) 结束时自动停止 vLLM。

#### 参数说明

| 变量 / 参数 | 含义 | 示例 |
|-------------|------|------|
| `MODEL` | 本地 merged 模型路径（给 vLLM serve + tokenizer） | `/path/to/your/merged_model` |
| `--glm-base-url` | 大模型 / 接力模型的 OpenAI 兼容 API 地址 | `http://your-glm-host:8000/v1` |
| `--glm-api-key` | 该接口的 API Key | `your-glm-api-key` |
| `--glm-model` | GLM 侧已部署的模型名 | `your-glm-model` |
| `--output-dir` | 各数据集 JSON 结果输出目录 | `./results_500` |
| `--datasets` | 评测集（空格分隔） | `gsm8k minerva olympiad aime2024 aime2025` |

Tokenizer 必须包含特殊 token `<|llm_offload|>`。

---

## Results



---

## Citation


