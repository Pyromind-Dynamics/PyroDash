# pyroDash-eval

**Language / 语言:** [English](README.md) | [中文](README_zh.md)

Offload 数学评测流程：本地小模型（vLLM）先生成；若输出 `<|llm_offload|>`，则由更强的 GLM 接力续写；最终用 `\boxed{}` 打分。

## 目录结构

| 文件 | 作用 |
|------|------|
| `math_eval.sh` | 启动 vLLM，再跑评测 |
| `math_eval.py` | 主评测循环：构造 prompt → 小模型 → 可选 GLM 接力 → 打分 → 保存 JSON |
| `datasets_loader.py` | 加载评测集题目与答案（`get_dataset_handler`） |
| `boxed_socre.py` | 对 `\boxed{}` 答案打分（`compare_answer`、`score_boxed_answer` 等） |
| `llm_relay.py` | 把含 offload 标记的样本交给 GLM 续写（`complete_offload_batch`） |

### 关键函数

- **`datasets_loader.get_dataset_handler(name)`** — 返回对应 handler；调用 `load_data()` 得到 `(questions, answers)`。
- **`boxed_socre.compare_answer(response, answer)`** — 预测的 `\boxed{}` 与标准答案是否一致（内部用 `math_verify`）。
- **`llm_relay.complete_offload_batch(...)`** — 对含 `<|llm_offload|>` 的回复，用 GLM 继续生成。
- **`math_eval.run_dataset(...)`** — 跑完一个数据集，写出 `{dataset}_results.json`。

## 快速开始

1. 按下文修改 `math_eval.sh` 里的占位符。
2. 安装依赖：`pip install math_verify mathruler pylatexenc requests tqdm pandas datasets transformers`（GPU 机器还需 `vllm`）。
3. 运行：

```bash
bash math_eval.sh
```

结果保存在 `--output-dir`（脚本默认：`./results_500`）。

---

## `math_eval.sh` — 参数说明（重点）

脚本流程：(1) 在 `8001` 端口 `vllm serve` 小模型；(2) 调用 `math_eval.py`，传入同一模型路径与 GLM 接力配置。

### 必须修改（占位符）

| 变量 / 参数 | 含义 | 应传入什么 |
|-------------|------|------------|
| `MODEL` | 本地 merged 模型目录，同时给 `vllm serve` 和 tokenizer 用 | 你的 checkpoint 绝对路径，例如 `/path/to/your/merged_model` |
| `--glm-base-url` | 大模型 / 接力模型的 OpenAI 兼容 API 根地址 | 例如 `http://your-glm-host:8000/v1` |
| `--glm-api-key` | 该接口的 API Key | 例如 `your-glm-api-key`（按服务端要求填写） |
| `--glm-model` | GLM 侧已部署的模型名 | 例如 `your-glm-model`（需与远端 `--served-model-name` 一致） |

### 一般可沿用 / 按需调整

| 参数 | 含义 | 典型取值 |
|------|------|----------|
| `--model-path` | 同 `MODEL`，只用于加载 tokenizer / chat template | `"$MODEL"` |
| `--small-base-url` | 本地 vLLM 的 OpenAI API 根地址 | `http://127.0.0.1:8001/v1`（需与 serve 的 host/port 一致） |
| `--small-model` | 本地已 serve 的模型名 | `small-model`（需与 `vllm serve` 的 `--served-model-name` 一致） |
| `--output-dir` | 各数据集 JSON 结果输出目录 | 例如 `./results_500` |
| `--datasets` | 要跑的评测集（空格分隔） | 可选：`math` `gsm8k` `minerva` `olympiad` `aime2024` `aime2025` `amc` `mydataset` |
| `--max-tokens` | 小模型单次最大生成长度；同时也是 **small + GLM 合计** 的 completion 预算 | 例如 `8192` |
| `--glm-max-workers` | GLM 并发请求数（Python CLI 参数；默认 `.sh` 未写出） | 默认 `256` |

### 脚本中的 vLLM 段

| 设置 | 含义 |
|------|------|
| `CUDA_VISIBLE_DEVICES` | 使用哪张 GPU |
| `--port 8001` | 本地服务端口（需与 `--small-base-url` 一致） |
| `--served-model-name small-model` | 客户端调用时的模型名（需与 `--small-model` 一致） |
| `--max-model-len` | vLLM 上下文长度 |
| `--gpu-memory-utilization` | GPU 显存占用比例 |

---

## 填完之后的示例

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

Tokenizer 必须包含特殊 token `<|llm_offload|>`，否则 `math_eval.py` 会直接报错退出。
