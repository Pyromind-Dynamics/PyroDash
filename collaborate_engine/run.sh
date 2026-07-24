#!/usr/bin/env bash
# Edit the parameters below, then: ./run.sh
# Unified API: http://127.0.0.1:${PORT}/v1/chat/completions

set -euo pipefail

# ========== edit these ==========
SLM_BASE_URL="http://127.0.0.1:8001/v1"
SLM_API_KEY="EMPTY"
SLM_MODEL="PyroDash-4B"

LLM_BASE_URL="https://your-llm-host/v1"
LLM_API_KEY="your-key"
LLM_MODEL="your-llm-model"

EXPOSED_MODEL_NAME="pyrodash"
EXPOSED_API_KEY="sk-pyrodash"
HOST="0.0.0.0"
PORT="8100"
# ================================

ROOT="$(cd "$(dirname "$0")" && pwd)"
export PYTHONPATH="$ROOT"

exec python -m collaborate_engine.server \
  --slm-base-url "$SLM_BASE_URL" \
  --slm-api-key "$SLM_API_KEY" \
  --slm-model "$SLM_MODEL" \
  --llm-base-url "$LLM_BASE_URL" \
  --llm-api-key "$LLM_API_KEY" \
  --llm-model "$LLM_MODEL" \
  --exposed-model "$EXPOSED_MODEL_NAME" \
  --api-key "$EXPOSED_API_KEY" \
  --host "$HOST" \
  --port "$PORT"
