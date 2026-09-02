#!/usr/bin/env bash
# Start local vLLM (SLM) + offload adapter. Keep this process running.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CODE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
OUT="$CODE_DIR/output/miniswe_offload_verified"
mkdir -p "$OUT/adapter_stats"

export LD_LIBRARY_PATH="${CONDA_PREFIX:+$CONDA_PREFIX/lib${LD_LIBRARY_PATH:+:}}${LD_LIBRARY_PATH:-}"

MODEL=/path/to/your/slm_model

# ---------- 1) start vLLM (small model) ----------
CUDA_VISIBLE_DEVICES=0 vllm serve "$MODEL" \
  --host 127.0.0.1 \
  --port 8001 \
  --served-model-name small-model \
  --tensor-parallel-size 1 \
  --gpu-memory-utilization 0.9 \
  --max-model-len 128000 \
  --trust-remote-code \
  --reasoning-parser qwen3 \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  >"$OUT/vllm_serve.log" 2>&1 &
VLLM_PID=$!

# ---------- 2) start offload adapter ----------
python "$SCRIPT_DIR/serve_adapter.py" \
  --host 0.0.0.0 \
  --port 18022 \
  --slm-base-url http://127.0.0.1:8001/v1 \
  --slm-api-key dummy \
  --slm-model small-model \
  --llm-base-url http://your-llm-host:8000/v1 \
  --llm-api-key your-llm-api-key \
  --llm-model your-llm-model \
  --use-llm true \
  --max-new-tokens 8192 \
  --slm-config "$SCRIPT_DIR/config_yaml/slm.yaml" \
  --llm-config "$SCRIPT_DIR/config_yaml/llm.yaml" \
  --stats-dir "$OUT/adapter_stats" \
  >"$OUT/adapter.log" 2>&1 &
ADAPTER_PID=$!

trap 'echo "[cleanup] stopping adapter=$ADAPTER_PID vllm=$VLLM_PID"; kill "$ADAPTER_PID" "$VLLM_PID" 2>/dev/null || true; wait "$ADAPTER_PID" "$VLLM_PID" 2>/dev/null || true; echo "[cleanup] stopped"' EXIT INT TERM

echo "[vllm] starting... (logs: $OUT/vllm_serve.log)"
until curl -sf http://127.0.0.1:8001/v1/models >/dev/null; do sleep 2; done
echo "[vllm] ready"

echo "[adapter] starting... (logs: $OUT/adapter.log)"
until curl -sf http://127.0.0.1:18022/health >/dev/null; do sleep 1; done
echo "[adapter] ready on http://127.0.0.1:18022"
echo "[adapter] Ctrl-C to stop vLLM + adapter"

wait "$ADAPTER_PID" "$VLLM_PID"
