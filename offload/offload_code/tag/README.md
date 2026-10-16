# Tag offload

SLM emits `<|llm_offload|>N<|/llm_offload|>` inside thinking; adapter relays to the LLM.

```bash
# Local SLM: set MODEL_PATH (+ LLM_*)
# Remote SLM: set SLM_BASE_URL + SLM_MODEL + SLM_API_KEY (+ LLM_*)
bash api.sh
```

Modes (`OFFLOAD_MODE`): `handoff` | `rewrite` | `keep`.

Defaults: `ADAPTER_HOST=0.0.0.0`, `ADAPTER_PORT=18027`, `VLLM_PORT=8007`.

See [../README.md](../README.md) for the HTTP contract and token stats.
