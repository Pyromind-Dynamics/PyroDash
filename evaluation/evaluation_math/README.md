# evaluation_math

Math benchmark **client**. Collaborative inference (SLM completions + bare `<|llm_offload|>` + LLM relay) is provided by [`offload/offload_math`](../../offload/offload_math/README.md). This directory only:

数学基准评测**客户端**。协同推理由 [`offload/offload_math`](../../offload/offload_math/README.md) 提供；本目录只负责：

1. Load datasets / 加载数据集  
2. Call adapter `POST /v1/math/complete` / 调用 adapter  
3. `\boxed{}` scoring and write JSON / `\boxed{}` 判分并写出 JSON  

## Dependencies / 依赖

```bash
# Repo root + this folder (math scoring / datasets)
# 仓库根 + 本目录（数学判分 / 数据集）
pip install -r requirements.txt -r evaluation/evaluation_math/requirements.txt
# Optional adapter deps (same vLLM env) / adapter 额外依赖（可选）
pip install -r offload/offload_math/requirements.txt
```

## Prerequisites / 前置

```bash
# Terminal 1: start adapter (starts local vLLM if needed)
# 终端 1：起 adapter（会按需拉起本地 vLLM）
MODEL_PATH=/path/to/math_slm \
LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash offload/offload_math/api.sh
```

Default adapter / 默认 adapter：`http://127.0.0.1:18031`。

## Run / 运行

```bash
# Defaults overridable via env / 默认 datasets / 端口可用环境变量覆盖
bash evaluation/evaluation_math/math_eval.sh

# Or explicit / 或显式：
ADAPTER_PORT=18031 OUTPUT_DIR=./my_results \
DATASETS="gsm8k minerva olympiad aime2024 aime2025" \
  bash evaluation/evaluation_math/math_eval.sh

python evaluation/evaluation_math/math_eval.py \
  --adapter-host 127.0.0.1 \
  --adapter-port 18031 \
  --output-dir ./results \
  --datasets gsm8k minerva \
  --max-tokens 8192
```

## Datasets / 数据集

`math` / `gsm8k` / `amc` / `minerva` / `olympiad` / `aime2024` / `aime2025`（见 `datasets_loader.py`）。

## Output / 输出

One `{output_dir}/{name}_results.json` per dataset:  
每个数据集一份 `{output_dir}/{name}_results.json`：

- `summary`：accuracy、offload_rate、SLM/LLM token totals, etc. / 合计等  
- `samples`：question, raw / completed, usage, score / 题目、raw / completed、usage、score  

Default output dir / 默认输出目录：`evaluation/evaluation_math/output/results`（ignored by root `.gitignore` `output/`）。

## Files / 文件

| File / 文件 | Role / 作用 |
|-------------|-------------|
| `math_eval.sh` | Health-check adapter then call Python / 探活后调 Python |
| `math_eval.py` | Concurrent adapter requests + scoring / 并发请求 + 判分 |
| `datasets_loader.py` | Dataset loading / 数据集加载 |
| `boxed_socre.py` | `\boxed{}` answer compare / 答案比对 |
