# Entropy offload / Entropy Offload

Routes by mean thinking-token entropy (top-k logprobs). If mean entropy > `ENTROPY_THRESHOLD`, drop the SLM turn and let the LLM rewrite.  
按 thinking token 平均熵（top-k logprobs）路由。若平均熵 > `ENTROPY_THRESHOLD`，丢弃本轮 SLM 输出，由 LLM 重写。

```bash
# Local SLM: set MODEL_PATH (+ LLM_* / ENTROPY_*)
# Remote SLM: set SLM_BASE_URL + SLM_MODEL + SLM_API_KEY (must support logprobs)
# 本地：设 MODEL_PATH；远程：需支持 logprobs
bash api.sh
```

Local vLLM sets `--max-logprobs` ≥ `ENTROPY_TOP_K` automatically. Remote SLM must expose top-k logprobs.  
本地 vLLM 会自动设置 `--max-logprobs` ≥ `ENTROPY_TOP_K`。远程小模型必须提供 top-k logprobs。

Defaults / 默认: `ADAPTER_HOST=0.0.0.0`, `ADAPTER_PORT=18028`, `VLLM_PORT=8008`.

See [../README.md](../README.md) for the HTTP contract and token stats.  
HTTP 约定与 token 统计见上级 [README](../README.md)。
