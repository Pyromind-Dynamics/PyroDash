# offload_math

**SLM + LLM offload adapter** for math: exposes an HTTP service. Internally uses the small model’s **`/v1/completions`** (`stop=["<|llm_offload|>"]`), then chat-relays to the large model when a bare `<|llm_offload|>` is detected. Eval scripts are clients only — not in this package.

数学场景的 **SLM + LLM offload adapter**：对外起 HTTP 服务。内部走小模型 **`/v1/completions`**（`stop=["<|llm_offload|>"]`），检测到裸标记 `<|llm_offload|>` 后再向大模型做 chat relay。评测脚本只做客户端，不在此包内。

Unlike `offload_code`, math does **not** use `<|llm_offload|>N<|/llm_offload|>`, and does **not** expose OpenAI chat as the primary API.  
与 `offload_code` 不同：数学侧 **不** 使用带 N 的控制符，也 **不** 暴露 OpenAI chat 作为主接口。

## Default ports / 默认端口

| Service / 服务 | Port / 端口 |
|----------------|-------------|
| Local vLLM (SLM) / 本地 vLLM（小模型） | `8001` |
| Math adapter | `18031` |

## Launch / 启动

```bash
# Local weights (starts vLLM) / 本地权重（会拉起 vLLM）
MODEL_PATH=/path/to/math_slm \
LLM_BASE_URL=https://your-llm-host/v1 LLM_API_KEY=... LLM_MODEL=... \
  bash offload/offload_math/api.sh

# Or remote SLM API (still need TOKENIZER_PATH / MODEL_PATH for chat template)
# 或远程小模型 API（仍需 TOKENIZER_PATH / MODEL_PATH 做 chat template）
SLM_BASE_URL=http://slm:8000/v1 SLM_MODEL=my-slm TOKENIZER_PATH=/path/to/weights \
LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash offload/offload_math/api.sh

# SLM-only baseline / 纯小模型基线
USE_LLM=false MODEL_PATH=/path/to/math_slm bash offload/offload_math/api.sh
```

## Client API / 客户端 API

| Endpoint | Purpose / 作用 |
|----------|----------------|
| `GET /health` | Liveness / 探活 |
| `GET /stats` | SLM/LLM token + offload counters / 计数 |
| `POST /v1/math/complete` | Single question: completions → optional relay / 单题 |
| `POST /v1/math/complete_batch` | Batch (sequential) / 批量（顺序） |

Example / 示例：

```bash
curl -sS http://127.0.0.1:18031/v1/math/complete \
  -H 'Content-Type: application/json' \
  -d '{"question":"1+1=?","max_tokens":256}'
```

Response fields / 返回字段：`raw_response`、`completed_response`、`has_offload`、`slm_usage`、`llm_usage`。

## Env vars (`api.sh`) / 环境变量

- SLM: `MODEL_PATH` **or** `SLM_BASE_URL` + `SLM_MODEL` (+ `SLM_API_KEY`)
- Tokenizer: `TOKENIZER_PATH` (defaults to `MODEL_PATH`) · 默认同 `MODEL_PATH`
- LLM: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`; `USE_LLM=false` skips relay · 跳过 relay
- Ports: `VLLM_PORT` (default 8001), `ADAPTER_PORT` (default 18031)
- `MAX_NEW_TOKENS`, `MAX_MODEL_LEN` (default 40960), sampling temperature, etc.

## Evaluation / 评测

Start this API first, then / 先起本 API，再：

```bash
bash evaluation/evaluation_math/math_eval.sh
# or
python evaluation/evaluation_math/math_eval.py --adapter-port 18031
```

See [`evaluation/evaluation_math/README.md`](../../evaluation/evaluation_math/README.md).
