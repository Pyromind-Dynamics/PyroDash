# pyroDash

**Language / 语言:** [English](README.md) | [中文](README_zh.md)

<a href="https://PyroMind-Dynamics.github.io/pyroDash-evaluate/"><img src="https://img.shields.io/badge/🌐%20Website-GitHub%20Pages-blue"/></a>&nbsp;&nbsp;<a href="#-citation"><img src="https://img.shields.io/badge/📄%20Paper-Preprint-blue"/></a>&nbsp;&nbsp;<a href="https://huggingface.co/datasets/pyromind/easyhard-24k"><img src="https://img.shields.io/badge/🤗%20Dataset-EasyHard--24K-yellow"/></a>&nbsp;&nbsp;<a href="https://huggingface.co/pyromind"><img src="https://img.shields.io/badge/🤗%20HuggingFace-pyromind-yellow"/></a>&nbsp;&nbsp;<a href="https://pyromind.ai/"><img src="https://img.shields.io/badge/🚀%20Quick%20Reproduce-PyroMind-orange"/></a>

---

> **一键复现：** 打开 [PyroMind Console](https://pyromind.ai/)，即可端到端快速复现评测。训练数据见 Hugging Face：[EasyHard-24K](https://huggingface.co/datasets/pyromind/easyhard-24k)。

<table>
<tr>
<td width="50%" valign="top">
<img src="./figs/fig_inference_architecture.png" alt="Inference Architecture" width="100%"/>
</td>
<td width="50%" valign="top">

我们提出 **PyroDash**，一种面向小模型与大模型协同推理的 Token 级动态推理范式。小模型在自回归流式解码中自行输出控制符 `<|llm_offload|>`，协同引擎据此将局部推理链一次性转交大模型补全。无需外接 Router 模型，亦无需重训练大模型，并兼容闭源大模型服务。

</td>
</tr>
</table>

训练上，PyroDash 采用三阶段渐进式优化管线：（1）训练控制符嵌入层，使小模型具备基本的 offload 表达能力；（2）冷启动 offload 能力，建立大小模型协作模式；（3）以 GRPO 强化学习联合优化动态 offload 策略，结合任务准确率奖励与大模型调用成本惩罚，在推理质量与算力成本之间取得自适应平衡。更多细节请见下方论文引用。

---

## 🚀 快速开始

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

## 📊 Results

<p align="center">
  <img src="./figs/fig_cost_accuracy_pareto.png" alt="Cost–Accuracy Pareto" width="70%"/>
</p>

---

## 🔗 相关资源

| 资源 | 链接 |
|------|------|
| 项目官网 | [PyroMind-Dynamics.github.io/pyroDash-evaluate](https://PyroMind-Dynamics.github.io/pyroDash-evaluate/) |
| 论文 | Preprint — 见 [Citation](#-citation) |
| 数据集（EasyHard-24K） | [huggingface.co/datasets/pyromind/easyhard-24k](https://huggingface.co/datasets/pyromind/easyhard-24k) |
| Hugging Face 组织 | [huggingface.co/pyromind](https://huggingface.co/pyromind) |
| PyroMind Console | [pyromind.ai](https://pyromind.ai/) |

---

## 📖 Citation

如果本工作对你有帮助，请引用：

```bibtex
@misc{pyrodash2026,
  title        = {PyroDash: Cost-Efficient Token-Level Small-Large Model Collaborative Inference},
  author       = {{PyroMind Dynamics}},
  year         = {2026},
  note         = {Preprint}
}
```

数据集：

```bibtex
@misc{pyromind2026easyhard24k,
  title        = {{EasyHard-24K} v0.02},
  author       = {{PyroMind Dynamics}},
  year         = {2026},
  howpublished = {\url{https://huggingface.co/datasets/pyromind/easyhard-24k}}
}
```
