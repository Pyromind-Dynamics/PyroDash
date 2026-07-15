#!/usr/bin/env bash
set -euo pipefail
export LD_LIBRARY_PATH="$CONDA_PREFIX/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"

MODEL=/path/to/your/merged_model

# ---------- 1) start vLLM (small model) ----------
CUDA_VISIBLE_DEVICES=0 vllm serve "$MODEL" \
  --host 127.0.0.1 \
  --port 8001 \
  --served-model-name small-model \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.9 \
  --max-model-len 40960 \
  --trust-remote-code \
  >./vllm_serve.log 2>&1 &
VLLM_PID=$!
trap 'echo "[vllm] stopping pid=$VLLM_PID"; kill "$VLLM_PID" 2>/dev/null || true; wait "$VLLM_PID" 2>/dev/null || true; echo "[vllm] stopped"' EXIT

# wait until ready
echo "[vllm] starting... (logs: ./vllm_serve.log)"
until curl -sf http://127.0.0.1:8001/v1/models >/dev/null; do sleep 2; done
echo "[vllm] ready"

# ---------- 2) evaluate with that vLLM ----------
python "$(dirname "$0")/math_eval.py" \
  --model-path "$MODEL" \
  --small-base-url http://127.0.0.1:8001/v1 \
  --small-model small-model \
  --output-dir ./results_500 \
  --datasets gsm8k minerva olympiad aime2024 aime2025 \
  --glm-base-url http://your-glm-host:8000/v1 \
  --glm-api-key your-glm-api-key \
  --glm-model your-glm-model \
  --max-tokens 8192   # small max_tokens; also total completion budget for small+glm

# ---------- 3) stop vLLM ----------
trap - EXIT
echo "[vllm] stopping pid=$VLLM_PID"
kill "$VLLM_PID" 2>/dev/null || true
wait "$VLLM_PID" 2>/dev/null || true
echo "[vllm] stopped"
