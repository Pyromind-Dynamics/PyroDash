# offload_code

Standalone **code offload adapters**: start a public HTTP API that wraps an SLM (local vLLM **or** remote OpenAI-compatible API) and relays to a remote LLM. Evaluation harnesses and web UIs are **clients** of this API — they are not part of this package.

## Mechanisms

| Dir | Trigger | Default ports |
|-----|---------|---------------|
| [`tag/`](tag/) | SLM emits `<\|llm_offload\|>N<\|\llm_offload\|>` inside thinking | vLLM `8007`, adapter `18027` |
| [`entropy/`](entropy/) | Mean thinking-token entropy (top-k logprobs) > threshold → LLM rewrite | vLLM `8008`, adapter `18028` |

Each tree is independently launchable (`api.sh`). [`shared/`](shared/) holds merged reference helpers (`protocol`, `openai_api`, `stats`, `tools`); runtime adapters under `tag/` / `entropy/` stay self-contained.

## Quick start

```bash
# Local SLM weights (starts vLLM):
MODEL_PATH=/path/to/slm LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash offload/offload_code/tag/api.sh

# Or remote SLM API (skip vLLM):
SLM_BASE_URL=http://slm-host:8000/v1 SLM_API_KEY=... SLM_MODEL=my-slm \
  LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
  bash offload/offload_code/tag/api.sh
```

Defaults bind **`0.0.0.0`** so other machines / a future web UI can reach the adapter.

## Client API (any benchmark)

Once ready:

| Endpoint | Purpose |
|----------|---------|
| `GET /health` | Liveness |
| `GET /stats` | Live SLM/LLM token + offload counters |
| `POST /v1/chat/completions` | OpenAI-compatible (primary for mini-extra) |
| `POST /v1/messages` | Anthropic-compatible |

Point any client at:

```text
api_base = http://<host>:<ADAPTER_PORT>
api_key  = dummy   # or any non-empty string
```

vLLM uses the **Qwen default chat template** (no custom jinja).

## Token accounting

Every request records API `usage` separately for SLM and LLM (no estimates):

- `slm_prompt_tokens` / `slm_completion_tokens`
- `llm_prompt_tokens` / `llm_completion_tokens`
- `offload_count`

Persisted under `logs/<run>/adapter_stats/` (`summary.json`, `sessions/`, `token_usage/`). Also available via `GET /stats`.

## Config knobs (`api.sh`)

Common:

- SLM (one of):
  - `MODEL_PATH` — local weights; script starts vLLM (`CUDA_VISIBLE_DEVICES`, `VLLM_HOST`/`VLLM_PORT`)
  - `SLM_BASE_URL` + `SLM_MODEL` (+ `SLM_API_KEY`) — remote OpenAI-compatible SLM; no local vLLM
- LLM: `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`
- `ADAPTER_HOST` / `ADAPTER_PORT` (default `0.0.0.0`)
- SLM / LLM sampling, `MAX_NEW_TOKENS`, `MAX_MODEL_LEN`

Tag-only: `OFFLOAD_MODE=handoff|rewrite|keep`

Entropy-only: `ENTROPY_TOP_K`, `ENTROPY_THRESHOLD`, `LLM_REASONING_EFFORT`

Optional: `PYTHON_BIN`, `VLLM_BIN`, `TOKEN_USAGE_DIR` (extra token_usage mirror).

## Dependencies

```bash
pip install -r requirements.txt
# plus a working `vllm` on PATH (or set VLLM_BIN)
```
