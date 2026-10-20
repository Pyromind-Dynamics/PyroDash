# Tag offload / Tag Offload

SLM emits `<|llm_offload|>N<|/llm_offload|>` inside thinking; adapter relays to the LLM.  
小模型在 thinking 中发出 `<|llm_offload|>N<|/llm_offload|>`，adapter 转交大模型。

```bash
# Local SLM: set MODEL_PATH (+ LLM_*)
# Remote SLM: set SLM_BASE_URL + SLM_MODEL + SLM_API_KEY (+ LLM_*)
# 本地：设 MODEL_PATH；远程：设 SLM_BASE_URL + SLM_MODEL + SLM_API_KEY
bash api.sh
```

Modes (`OFFLOAD_MODE`): `handoff` | `rewrite` | `keep`.  
模式（`OFFLOAD_MODE`）：`handoff` | `rewrite` | `keep`。

Defaults / 默认: `ADAPTER_HOST=0.0.0.0`, `ADAPTER_PORT=18027`, `VLLM_PORT=8007`.

See [../README.md](../README.md) for the HTTP contract and token stats.  
HTTP 约定与 token 统计见上级 [README](../README.md)。
