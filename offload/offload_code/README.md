# offload_code

Standalone **code offload adapters**: start a public HTTP API that wraps an SLM (local **vLLM / SGLang** **or** remote OpenAI-compatible API) and relays to a remote LLM. Evaluation harnesses and web UIs are **clients** of this API — they are not part of this package.

独立的 **代码 offload adapter**：对外起 HTTP API，封装小模型（本地 **vLLM / SGLang** 或远程 OpenAI 兼容 API）并向大模型 relay。评测 harness 与网页端是本 API 的**客户端**，不属于本包。

## Mechanisms / 机制

| Dir | Trigger / 触发 | Default ports / 默认端口 |
|-----|----------------|--------------------------|
| [`tag/`](tag/) | SLM emits `<\|llm_offload\|>N<\|\llm_offload\|>` inside thinking · thinking 内发出控制符 | SLM `8007`, adapter `18027` |
| [`entropy/`](entropy/) | Mean thinking-token entropy (top-k logprobs) > threshold → LLM rewrite · 平均熵超阈值则 LLM 重写 | SLM `8008`, adapter `18028` |

Each tree is independently launchable (`api.sh`). [`shared/`](shared/) holds merged reference helpers (`protocol`, `openai_api`, `stats`, `tools`); runtime adapters under `tag/` / `entropy/` stay self-contained.  
各目录可独立启动（`api.sh`）。[`shared/`](shared/) 为合并后的参考辅助代码；`tag/` / `entropy/` 运行时仍自包含。

## Quick start / 快速开始

```bash
# Local SLM weights (default SLM_BACKEND=vllm) / 本地权重
MODEL_PATH=/path/to/slm LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash offload/offload_code/tag/api.sh

# Local SGLang (tools + OpenAI /v1; entropy needs chat logprobs)
MODEL_PATH=/path/to/slm SLM_BACKEND=sglang \
  LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash offload/offload_code/tag/api.sh

# Or remote SLM API (skip local engine) / 远程小模型 API（不启本地引擎）
SLM_BASE_URL=http://slm-host:8000/v1 SLM_API_KEY=... SLM_MODEL=my-slm \
  LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash offload/offload_code/tag/api.sh
```

Defaults bind **`0.0.0.0`** so other machines / a future web UI can reach the adapter.  
默认绑定 **`0.0.0.0`**，方便其他机器或网页端访问。

## Client API (any benchmark) / 客户端 API（任意评测）

Once ready / 就绪后：

| Endpoint | Purpose / 作用 |
|----------|----------------|
| `GET /health` | Liveness / 探活 |
| `GET /stats` | Live SLM/LLM token + offload counters / 实时计数 |
| `POST /v1/chat/completions` | OpenAI-compatible (primary for mini-extra) |
| `POST /v1/messages` | Anthropic-compatible |

Point any client at / 客户端指向：

```text
api_base = http://<host>:<ADAPTER_PORT>
api_key  = dummy   # or any non-empty string · 任意非空字符串即可
```

Local vLLM/SGLang use the **Qwen default chat template** (no custom jinja) plus tool/reasoning parsers (`TOOL_CALL_PARSER`, `REASONING_PARSER`).  
本地 vLLM/SGLang 使用 **Qwen 默认 chat template**（无自定义 jinja）加上 tool/reasoning parser。

## Token accounting / Token 统计

Every request records API `usage` separately for SLM and LLM (no estimates):  
每次请求分别记录 SLM / LLM 的 API `usage`（无估算）：

- `slm_prompt_tokens` / `slm_completion_tokens`
- `llm_prompt_tokens` / `llm_completion_tokens`
- `offload_count`

Persisted under `logs/<run>/adapter_stats/` (`summary.json`, `sessions/`, `token_usage/`). Also via `GET /stats`.  
落盘于 `logs/<run>/adapter_stats/`；也可通过 `GET /stats` 查看。

## Config knobs (`api.sh`) / 配置项

Common / 通用:

- SLM (one of / 二选一):
  - `MODEL_PATH` — local weights; starts `SLM_BACKEND` (`vllm`|`sglang`) on `SLM_PORT` (alias `VLLM_PORT`) · 本地权重并拉起引擎
  - `SLM_BASE_URL` + `SLM_MODEL` (+ `SLM_API_KEY`) — remote OpenAI-compatible SLM; no local engine · 远程小模型
- Engine: `SLM_BACKEND`, `SLM_PORT`, `CUDA_VISIBLE_DEVICES`, `MAX_MODEL_LEN`, plus `VLLM_EXTRA_ARGS` / `SGLANG_EXTRA_ARGS`
- LLM: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`
- `ADAPTER_HOST` / `ADAPTER_PORT` (default `0.0.0.0`)
- SLM / LLM sampling, `MAX_NEW_TOKENS`, `MAX_MODEL_LEN`

Tag-only / 仅 tag: `OFFLOAD_MODE=handoff|rewrite|keep`

Entropy-only / 仅 entropy: `ENTROPY_TOP_K`, `ENTROPY_THRESHOLD`, `LLM_REASONING_EFFORT` (vLLM also sets `--max-logprobs`)

Required from caller (`run_use`): `PYTHON_BIN` (and `VLLM_BIN` / `SGLANG_*` when starting a local SLM). Optional: `TOKEN_USAGE_DIR`.  
调用方（`run_use`）需提供 `PYTHON_BIN`（本地起小模型时还需 `VLLM_BIN` / `SGLANG_*`）。可选：`TOKEN_USAGE_DIR`。

Do **not** set env paths inside `offload/` — use the web UI / [`run_use/run_sh/run_coding.sh`](../../run_use/run_sh/run_coding.sh).  
**不要**在 `offload/` 内写死环境路径 —— 用网页或 `run_coding.sh`。

## Dependencies / 依赖

```bash
# In your SLM/vLLM env / 在 SLM/vLLM 环境中:
pip install -r requirements.txt
# plus a working `vllm` (or set VLLM_BIN); for SGLang: pip install sglang
```
