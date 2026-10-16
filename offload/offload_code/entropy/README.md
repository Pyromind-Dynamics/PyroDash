# Entropy offload

Routes by mean thinking-token entropy (top-k logprobs). If mean entropy > `ENTROPY_THRESHOLD`, drop the SLM turn and let the LLM rewrite.

```bash
# Local SLM: set MODEL_PATH (+ LLM_* / ENTROPY_*)
# Remote SLM: set SLM_BASE_URL + SLM_MODEL + SLM_API_KEY (must support logprobs)
bash api.sh
```

Local vLLM sets `--max-logprobs` ≥ `ENTROPY_TOP_K` automatically. Remote SLM must expose top-k logprobs.

Defaults: `ADAPTER_HOST=0.0.0.0`, `ADAPTER_PORT=18028`, `VLLM_PORT=8008`.

See [../README.md](../README.md) for the HTTP contract and token stats.
