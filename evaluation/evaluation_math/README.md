# evaluation_math

数学基准评测客户端。协同推理（小模型 completions + 裸 `<|llm_offload|>` + 大模型 relay）由 [`offload/offload_math`](../../offload/offload_math/README.md) 提供；本目录只负责：

1. 加载数据集  
2. 调用 adapter `POST /v1/math/complete`  
3. `\boxed{}` 判分并写出 JSON  

## 前置

```bash
# 终端 1：起 adapter（会按需拉起本地 vLLM）
MODEL_PATH=/path/to/math_slm \
LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash offload/offload_math/api.sh
```

默认 adapter：`http://127.0.0.1:18031`。

## 运行

```bash
# 默认 datasets / 端口可用环境变量覆盖
bash evaluation/evaluation_math/math_eval.sh

# 或显式：
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

## 数据集

`math` / `gsm8k` / `amc` / `minerva` / `olympiad` / `aime2024` / `aime2025`（见 `datasets_loader.py`）。

## 输出

每个数据集一份 `{output_dir}/{name}_results.json`：

- `summary`：accuracy、offload_rate、SLM/LLM token 合计等  
- `samples`：题目、raw / completed、usage、score  

默认输出目录：`evaluation/evaluation_math/output/results`（已由仓库根 `.gitignore` 的 `output/` 忽略）。

## 文件

| 文件 | 作用 |
|------|------|
| `math_eval.sh` | 探活 adapter 后调 Python |
| `math_eval.py` | 并发请求 adapter + 判分 |
| `datasets_loader.py` | 数据集加载 |
| `boxed_socre.py` | `\boxed{}` 答案比对 |
