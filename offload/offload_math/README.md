# offload_math

数学场景的 **SLM + LLM offload adapter**：对外起 HTTP 服务。内部走小模型 **`/v1/completions`**（`stop=["<|llm_offload|>"]`），检测到裸标记 `<|llm_offload|>` 后再向大模型做 chat relay。评测脚本只做客户端，不在此包内。

与 `offload_code` 不同：数学侧 **不** 使用 `<|llm_offload|>N<|/llm_offload|>`，也 **不** 暴露 OpenAI chat 作为主接口。

## 默认端口

| 服务 | 端口 |
|------|------|
| 本地 vLLM（小模型） | `8001` |
| Math adapter | `18031` |

## 启动

```bash
# 本地权重（会拉起 vLLM）
MODEL_PATH=/path/to/math_slm \
LLM_BASE_URL=https://your-llm-host/v1 LLM_API_KEY=... LLM_MODEL=... \
  bash offload/offload_math/api.sh

# 或远程小模型 API（仍需 TOKENIZER_PATH / MODEL_PATH 做 chat template）
SLM_BASE_URL=http://slm:8000/v1 SLM_MODEL=my-slm TOKENIZER_PATH=/path/to/weights \
LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash offload/offload_math/api.sh

# 纯小模型基线
USE_LLM=false MODEL_PATH=/path/to/math_slm bash offload/offload_math/api.sh
```

## 客户端 API

| 接口 | 作用 |
|------|------|
| `GET /health` | 探活 |
| `GET /stats` | SLM/LLM token 与 offload 计数 |
| `POST /v1/math/complete` | 单题：completions → 可选 relay |
| `POST /v1/math/complete_batch` | 批量（顺序处理） |

示例：

```bash
curl -sS http://127.0.0.1:18031/v1/math/complete \
  -H 'Content-Type: application/json' \
  -d '{"question":"1+1=?","max_tokens":256}'
```

返回字段：`raw_response`、`completed_response`、`has_offload`、`slm_usage`、`llm_usage`。

## 环境变量（`api.sh`）

- SLM：`MODEL_PATH` **或** `SLM_BASE_URL` + `SLM_MODEL`（+ `SLM_API_KEY`）
- Tokenizer：`TOKENIZER_PATH`（默认同 `MODEL_PATH`）
- LLM：`LLM_BASE_URL`、`LLM_API_KEY`、`LLM_MODEL`；`USE_LLM=false` 跳过 relay
- 端口：`VLLM_PORT`（默认 8001）、`ADAPTER_PORT`（默认 18031）
- `MAX_NEW_TOKENS`、`MAX_MODEL_LEN`（默认 40960）、采样温度等

## 评测

先起本 API，再：

```bash
bash evaluation/evaluation_math/math_eval.sh
# 或
python evaluation/evaluation_math/math_eval.py --adapter-port 18031
```

见 [`evaluation/evaluation_math/README.md`](../../evaluation/evaluation_math/README.md)。
