#!/usr/bin/env bash
# smoke：swe 只跑 1 题 + slm_only（本地 SLM，不走 LLM offload）
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_CODING="${SCRIPT_DIR}/../run_coding.sh"

# --- 模式 ---
export MODE=swe_20filter
export ROUTER_MODE=slm_only          # run_coding.sh 会转成 tag adapter + USE_LLM=false
export CLUSTER=us
export USE_LLM=false                 # 显式写出，与 slm_only 一致

# --- Python 环境 ---
export VLLM_ENV=/workspace/work/mjy/.venv
export HARNESS_PYTHON=/workspace/.conda/bin/python
export PATH="/root/.local/bin:${PATH}"   # mini-extra

# --- 小模型（本地权重 → vLLM）---
export MODEL_PATH=/workspace/work/mjy/models/agent_offload_pyrodash4b_sft0918_gigpo_20261012_101437/iter_0000139
export SLM_BACKEND=vllm
export CUDA_VISIBLE_DEVICES=0
export SLM_PORT=8007
export ADAPTER_PORT=18027
export ADAPTER_HOST=0.0.0.0

# --- LLM 占位（slm_only 不会真正调用，但 run_coding 仍会 export）---
export LLM_BASE_URL=http://127.0.0.1:0/v1
export LLM_API_KEY=dummy
export LLM_MODEL=unused

# --- smoke：只跑 1 个 instance，覆盖默认 20 题 filter ---
export INSTANCE_FILTER=astropy__astropy-14182
export WORKERS=1
export HARNESS_WORKERS=1
export STEP_LIMIT=150

# --- 可选：断点续跑时取消注释 ---
# export RUN_ID=my_swe_smoke_slmonly
# export RESUME=1

exec bash "${RUN_CODING}" "$@"
