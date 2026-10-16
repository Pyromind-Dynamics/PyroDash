#!/usr/bin/env bash
# Start entropy-routing adapter. Edit the config block, then: bash api.sh
# Ctrl+C stops adapter (+ local vLLM if started).
#
# SLM can be:
#   A) local weights  — set MODEL_PATH (directory); this script starts vLLM
#   B) remote API     — set SLM_BASE_URL + SLM_MODEL (+ SLM_API_KEY); skip vLLM
#
# Routing: mean thinking-token entropy (top-k logprobs, nats) > ENTROPY_THRESHOLD
# -> drop SLM turn and let the LLM rewrite.
# Remote SLM must support logprobs / top_logprobs (vLLM --max-logprobs).
set -euo pipefail

OFFLOAD_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || command -v python)}"

# =========================
# Edit this block (or export env vars before running)
# =========================

# --- Small model (pick ONE) ---
# A) Local path → start vLLM on VLLM_HOST:VLLM_PORT
MODEL_PATH="${MODEL_PATH:-}"
# B) Remote OpenAI-compatible SLM (if SLM_BASE_URL is set, MODEL_PATH is ignored)
SLM_BASE_URL="${SLM_BASE_URL:-}"
SLM_API_KEY="${SLM_API_KEY:-dummy}"
SLM_MODEL="${SLM_MODEL:-}"

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

# Remote LLM (OpenAI-compatible)
LLM_BASE_URL="${LLM_BASE_URL:-https://your-llm-host/v1}"
LLM_API_KEY="${LLM_API_KEY:-your-llm-api-key}"
LLM_MODEL="${LLM_MODEL:-your-llm-model}"
# LLM rewrite reasoning_effort; empty = omit field
LLM_REASONING_EFFORT="${LLM_REASONING_EFFORT:-max}"

# Network: bind 0.0.0.0 so external / web clients can reach the API
VLLM_HOST="${VLLM_HOST:-0.0.0.0}"
VLLM_PORT="${VLLM_PORT:-8008}"
ADAPTER_HOST="${ADAPTER_HOST:-0.0.0.0}"
ADAPTER_PORT="${ADAPTER_PORT:-18028}"

# Entropy routing (k=20 => entropy in [0, ln(20)≈2.996] nats)
ENTROPY_TOP_K="${ENTROPY_TOP_K:-20}"
ENTROPY_THRESHOLD="${ENTROPY_THRESHOLD:-0.1}"
export VLLM_MAX_LOGPROBS="${VLLM_MAX_LOGPROBS:-${ENTROPY_TOP_K}}"

# --- SLM sampling ---
SLM_TEMPERATURE="${SLM_TEMPERATURE:-0.6}"
SLM_TOP_P="${SLM_TOP_P:-0.95}"
SLM_TOP_K="${SLM_TOP_K:-20}"
SLM_MIN_P="${SLM_MIN_P:-0.0}"
SLM_PRESENCE_PENALTY="${SLM_PRESENCE_PENALTY:-0.0}"
SLM_REPETITION_PENALTY="${SLM_REPETITION_PENALTY:-1.0}"

# --- LLM sampling ---
LLM_TEMPERATURE="${LLM_TEMPERATURE:-1.0}"
LLM_TOP_P="${LLM_TOP_P:-1.0}"

MAX_NEW_TOKENS="${MAX_NEW_TOKENS:-8192}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-}"
# =========================

source "${OFFLOAD_ROOT}/serve/common.sh"
source "${OFFLOAD_ROOT}/serve/vllm.sh"
VLLM_HOST="${VLLM_HOST}"
VLLM_PORT="${VLLM_PORT}"
VLLM_MAX_MODEL_LEN="${MAX_MODEL_LEN}"

START_LOCAL_VLLM=0
if [[ -n "${SLM_BASE_URL}" ]]; then
  [[ -n "${SLM_MODEL}" ]] || { echo "ERROR: SLM_MODEL is required when SLM_BASE_URL is set" >&2; exit 1; }
  SERVED_NAME="${SLM_MODEL}"
  echo "[api] SLM mode=remote  ${SLM_MODEL} @ ${SLM_BASE_URL}"
elif [[ -n "${MODEL_PATH}" ]]; then
  [[ -d "${MODEL_PATH}" ]] || { echo "ERROR: MODEL_PATH missing: ${MODEL_PATH}" >&2; exit 1; }
  START_LOCAL_VLLM=1
  SERVED_NAME="$(basename "${MODEL_PATH}")"
  SLM_BASE_URL="http://127.0.0.1:${VLLM_PORT}/v1"
  SLM_API_KEY="${SLM_API_KEY:-dummy}"
  SLM_MODEL="${SERVED_NAME}"
  echo "[api] SLM mode=local   ${MODEL_PATH} → vLLM :${VLLM_PORT}"
else
  echo "ERROR: set either MODEL_PATH (local) or SLM_BASE_URL+SLM_MODEL (remote API)" >&2
  exit 1
fi

[[ -n "${LLM_API_KEY}" && "${LLM_API_KEY}" != "your-llm-api-key" ]] || \
  echo "WARNING: set LLM_API_KEY before production use" >&2

RUN_STAMP="$(date '+%Y%m%d_%H%M%S')"
SAFE_NAME="$(echo "${SERVED_NAME}" | tr '/: ' '___')"
LOG_DIR="${OFFLOAD_ROOT}/logs/${SAFE_NAME}_${RUN_STAMP}"
mkdir -p "${LOG_DIR}/adapter_stats"

ADAPTER_PID=""
ADAPTER_LOG="${LOG_DIR}/adapter.log"

cleanup_adapter() {
  if [[ -n "${ADAPTER_PID}" ]] && kill -0 "${ADAPTER_PID}" 2>/dev/null; then
    echo "[adapter] stopping pid=${ADAPTER_PID}"
    kill "${ADAPTER_PID}" 2>/dev/null || true
    for _ in $(seq 1 20); do
      kill -0 "${ADAPTER_PID}" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "${ADAPTER_PID}" 2>/dev/null; then
      kill -9 "${ADAPTER_PID}" 2>/dev/null || true
    fi
    wait "${ADAPTER_PID}" 2>/dev/null || true
  fi
  ADAPTER_PID=""
}

cleanup_all() {
  cleanup_adapter
  if [[ "${START_LOCAL_VLLM}" -eq 1 ]]; then
    cleanup_vllm
  fi
}
trap cleanup_all EXIT INT TERM

wait_adapter_ready() {
  local url="http://127.0.0.1:${ADAPTER_PORT}/health"
  local deadline=$((SECONDS + 120))
  echo "[adapter] waiting for ${url}"
  while (( SECONDS < deadline )); do
    if ! kill -0 "${ADAPTER_PID}" 2>/dev/null; then
      echo "[adapter ERROR] exited early; see ${ADAPTER_LOG}" >&2
      return 1
    fi
    if curl -sf --max-time 2 "${url}" >/dev/null 2>&1; then
      echo "[adapter] ready"
      return 0
    fi
    sleep 1
  done
  echo "[adapter ERROR] not ready; see ${ADAPTER_LOG}" >&2
  return 1
}

start_adapter() {
  if [[ -n "${TOKEN_USAGE_DIR:-}" ]]; then
    mkdir -p "${TOKEN_USAGE_DIR}"
    export TOKEN_USAGE_DIR
  fi
  echo "[adapter] SLM=${SLM_MODEL} @ ${SLM_BASE_URL}"
  echo "[adapter] LLM=${LLM_MODEL} @ ${LLM_BASE_URL}"
  echo "[adapter] entropy top_k=${ENTROPY_TOP_K} threshold=${ENTROPY_THRESHOLD} (nats)"
  echo "[adapter] listen ${ADAPTER_HOST}:${ADAPTER_PORT}  log=${ADAPTER_LOG}"
  echo "[adapter] stats -> ${LOG_DIR}/adapter_stats"
  local -a effort_args=()
  if [[ -n "${LLM_REASONING_EFFORT}" ]]; then
    effort_args=(--llm-reasoning-effort "${LLM_REASONING_EFFORT}")
  fi
  "${PYTHON_BIN}" \
    "${OFFLOAD_ROOT}/serve_adapter.py" \
    --host "${ADAPTER_HOST}" \
    --port "${ADAPTER_PORT}" \
    --slm-base-url "${SLM_BASE_URL}" \
    --slm-api-key "${SLM_API_KEY}" \
    --slm-model "${SLM_MODEL}" \
    --llm-base-url "${LLM_BASE_URL}" \
    --llm-api-key "${LLM_API_KEY}" \
    --llm-model "${LLM_MODEL}" \
    --use-llm true \
    --max-new-tokens "${MAX_NEW_TOKENS}" \
    ${MAX_MODEL_LEN:+--max-context-len "${MAX_MODEL_LEN}"} \
    --slm-temperature "${SLM_TEMPERATURE}" \
    --slm-top-p "${SLM_TOP_P}" \
    --slm-top-k "${SLM_TOP_K}" \
    --slm-min-p "${SLM_MIN_P}" \
    --slm-presence-penalty "${SLM_PRESENCE_PENALTY}" \
    --slm-repetition-penalty "${SLM_REPETITION_PENALTY}" \
    --llm-temperature "${LLM_TEMPERATURE}" \
    --llm-top-p "${LLM_TOP_P}" \
    "${effort_args[@]}" \
    --entropy-top-k "${ENTROPY_TOP_K}" \
    --entropy-threshold "${ENTROPY_THRESHOLD}" \
    --stats-dir "${LOG_DIR}/adapter_stats" \
    >"${ADAPTER_LOG}" 2>&1 &
  ADAPTER_PID=$!
  wait_adapter_ready
}

if [[ "${START_LOCAL_VLLM}" -eq 1 ]]; then
  start_vllm "${MODEL_PATH}" "${SERVED_NAME}" "${LOG_DIR}"
fi
start_adapter

HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
HOST_IP="${HOST_IP:-127.0.0.1}"

SLM_LINE="  SLM             : ${SLM_MODEL} @ ${SLM_BASE_URL}"
if [[ "${START_LOCAL_VLLM}" -eq 1 ]]; then
  SLM_LINE="  vLLM SLM        : http://${HOST_IP}:${VLLM_PORT}/v1  (${SERVED_NAME})"
fi

cat <<EOF

========== Entropy offload API ready ==========
  adapter health : http://${HOST_IP}:${ADAPTER_PORT}/health
  adapter base   : http://${HOST_IP}:${ADAPTER_PORT}/v1
  adapter stats  : http://${HOST_IP}:${ADAPTER_PORT}/stats
${SLM_LINE}
  LLM            : ${LLM_MODEL} @ ${LLM_BASE_URL}
  entropy        : top_k=${ENTROPY_TOP_K}  threshold=${ENTROPY_THRESHOLD} nats
  token stats    : ${LOG_DIR}/adapter_stats/
  logs           : ${LOG_DIR}/
  Ctrl+C to stop

curl -sS http://${HOST_IP}:${ADAPTER_PORT}/v1/chat/completions \\
  -H 'Content-Type: application/json' \\
  -H 'Authorization: Bearer dummy' \\
  -d '{"model":"offload-router","messages":[{"role":"user","content":"ping"}],"max_tokens":256}'
===============================================

EOF

wait "${ADAPTER_PID}"
