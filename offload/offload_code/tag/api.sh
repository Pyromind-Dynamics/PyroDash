#!/usr/bin/env bash
# Start tag-offload adapter. Edit the config block, then: bash api.sh
# Ctrl+C stops adapter (+ local SLM server if started).
#
# SLM can be:
#   A) local weights  — set MODEL_PATH; starts vLLM or SGLang (SLM_BACKEND)
#   B) remote API     — set SLM_BASE_URL + SLM_MODEL (+ SLM_API_KEY); skip local serve
set -euo pipefail

OFFLOAD_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYRODASH_ROOT="$(cd "${OFFLOAD_ROOT}/../../.." && pwd)"
# Prefer project .venv for adapter / vLLM (same as run_use).
# shellcheck disable=SC1091
if [[ -f "${PYRODASH_ROOT}/env_paths.sh" ]]; then
  source "${PYRODASH_ROOT}/env_paths.sh"
  pyrodash_activate_venv "${VENV_DIR:-${PYRODASH_VENV_DIR}}"
else
  PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || command -v python)}"
fi
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || command -v python)}"

# =========================
# Edit this block (or export env vars before running)
# =========================

# --- Small model (pick ONE) ---
# A) Local path → start SLM_BACKEND on SLM_PORT
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

# Local engine: vllm | sglang
SLM_BACKEND="${SLM_BACKEND:-vllm}"
# Network: bind 0.0.0.0 so external / web clients can reach the API
SLM_HOST="${SLM_HOST:-${VLLM_HOST:-0.0.0.0}}"
SLM_PORT="${SLM_PORT:-${VLLM_PORT:-8007}}"
VLLM_HOST="${SLM_HOST}"
VLLM_PORT="${SLM_PORT}"
ADAPTER_HOST="${ADAPTER_HOST:-0.0.0.0}"
ADAPTER_PORT="${ADAPTER_PORT:-18027}"

# Tunables live in VLLM_EXTRA_ARGS / SGLANG_EXTRA_ARGS (CLI -- flags). Defaults in serve/*.sh.

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
# Empty = model default context. Set e.g. 128000 to cap both engine and adapter.
MAX_MODEL_LEN="${MAX_MODEL_LEN:-}"

# offload mode: handoff | rewrite | keep
OFFLOAD_MODE="${OFFLOAD_MODE:-handoff}"
# USE_LLM=false → SLM-only (no offload system prompt, no LLM call)
USE_LLM="${USE_LLM:-true}"
# =========================

case "${SLM_BACKEND}" in
  vllm|sglang) ;;
  *) echo "ERROR: SLM_BACKEND must be vllm or sglang (got ${SLM_BACKEND})" >&2; exit 1 ;;
esac

source "${OFFLOAD_ROOT}/serve/common.sh"
source "${OFFLOAD_ROOT}/serve/vllm.sh"
source "${OFFLOAD_ROOT}/serve/sglang.sh"
VLLM_HOST="${SLM_HOST}"
VLLM_PORT="${SLM_PORT}"
VLLM_MAX_MODEL_LEN="${MAX_MODEL_LEN}"
SGLANG_HOST="${SLM_HOST}"
SGLANG_PORT="${SLM_PORT}"

START_LOCAL_SLM=0
if [[ -n "${SLM_BASE_URL}" ]]; then
  [[ -n "${SLM_MODEL}" ]] || { echo "ERROR: SLM_MODEL is required when SLM_BASE_URL is set" >&2; exit 1; }
  SERVED_NAME="${SLM_MODEL}"
  echo "[api] SLM mode=remote  ${SLM_MODEL} @ ${SLM_BASE_URL}"
elif [[ -n "${MODEL_PATH}" ]]; then
  [[ -d "${MODEL_PATH}" ]] || { echo "ERROR: MODEL_PATH missing: ${MODEL_PATH}" >&2; exit 1; }
  START_LOCAL_SLM=1
  SERVED_NAME="$(basename "${MODEL_PATH}")"
  SLM_BASE_URL="http://127.0.0.1:${SLM_PORT}/v1"
  SLM_API_KEY="${SLM_API_KEY:-dummy}"
  SLM_MODEL="${SERVED_NAME}"
  echo "[api] SLM mode=local   ${MODEL_PATH} → ${SLM_BACKEND} :${SLM_PORT}"
else
  echo "ERROR: set either MODEL_PATH (local) or SLM_BASE_URL+SLM_MODEL (remote API)" >&2
  exit 1
fi

case "${USE_LLM}" in
  true|True|TRUE|1|yes|YES) USE_LLM=true ;;
  false|False|FALSE|0|no|NO) USE_LLM=false ;;
  *) echo "ERROR: USE_LLM must be true or false (got ${USE_LLM})" >&2; exit 1 ;;
esac
if [[ "${USE_LLM}" == "true" ]]; then
  [[ -n "${LLM_API_KEY}" && "${LLM_API_KEY}" != "your-llm-api-key" ]] || \
    echo "WARNING: set LLM_API_KEY before production use" >&2
else
  # Dummy placeholders so argparse still receives values when SLM-only
  LLM_BASE_URL="${LLM_BASE_URL:-http://127.0.0.1:0/v1}"
  LLM_API_KEY="${LLM_API_KEY:-unused}"
  LLM_MODEL="${LLM_MODEL:-unused}"
  echo "[api] USE_LLM=false → SLM-only (no offload system prompt)"
fi
case "${OFFLOAD_MODE}" in
  handoff|rewrite|keep) ;;
  *) echo "ERROR: OFFLOAD_MODE must be handoff, rewrite, or keep (got ${OFFLOAD_MODE})" >&2; exit 1 ;;
esac

RUN_STAMP="$(date '+%Y%m%d_%H%M%S')"
SAFE_NAME="$(echo "${SERVED_NAME}" | tr '/: ' '___')"
# OFFLOAD_LOG_DIR: when set (e.g. by run_use), put SLM/adapter logs there for the web UI.
LOG_DIR="${OFFLOAD_LOG_DIR:-${OFFLOAD_ROOT}/logs/${SAFE_NAME}_${OFFLOAD_MODE}_${RUN_STAMP}}"
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
  if [[ "${START_LOCAL_SLM}" -eq 1 ]]; then
    if [[ "${SLM_BACKEND}" == "sglang" ]]; then
      cleanup_sglang
    else
      cleanup_vllm
    fi
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
  echo "[adapter] LLM=${LLM_MODEL} @ ${LLM_BASE_URL}  use_llm=${USE_LLM}"
  echo "[adapter] offload mode=${OFFLOAD_MODE}"
  echo "[adapter] listen ${ADAPTER_HOST}:${ADAPTER_PORT}  log=${ADAPTER_LOG}"
  echo "[adapter] stats -> ${LOG_DIR}/adapter_stats"
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
    --use-llm "${USE_LLM}" \
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
    --offload-mode "${OFFLOAD_MODE}" \
    --stats-dir "${LOG_DIR}/adapter_stats" \
    >"${ADAPTER_LOG}" 2>&1 &
  ADAPTER_PID=$!
  wait_adapter_ready
}

if [[ "${START_LOCAL_SLM}" -eq 1 ]]; then
  if [[ "${SLM_BACKEND}" == "sglang" ]]; then
    start_sglang "${MODEL_PATH}" "${SERVED_NAME}" "${LOG_DIR}"
  else
    start_vllm "${MODEL_PATH}" "${SERVED_NAME}" "${LOG_DIR}"
  fi
fi
start_adapter

HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
HOST_IP="${HOST_IP:-127.0.0.1}"

SLM_LINE="  SLM             : ${SLM_MODEL} @ ${SLM_BASE_URL}"
if [[ "${START_LOCAL_SLM}" -eq 1 ]]; then
  SLM_LINE="  ${SLM_BACKEND} SLM    : http://${HOST_IP}:${SLM_PORT}/v1  (${SERVED_NAME})"
fi

cat <<EOF

========== Tag offload API ready ==========
  adapter health : http://${HOST_IP}:${ADAPTER_PORT}/health
  adapter base   : http://${HOST_IP}:${ADAPTER_PORT}/v1
  adapter stats  : http://${HOST_IP}:${ADAPTER_PORT}/stats
${SLM_LINE}
  LLM            : ${LLM_MODEL} @ ${LLM_BASE_URL}
  offload mode   : ${OFFLOAD_MODE}
  token stats    : ${LOG_DIR}/adapter_stats/
  logs           : ${LOG_DIR}/
  Ctrl+C to stop

curl -sS http://${HOST_IP}:${ADAPTER_PORT}/v1/chat/completions \\
  -H 'Content-Type: application/json' \\
  -H 'Authorization: Bearer dummy' \\
  -d '{"model":"offload-router","messages":[{"role":"user","content":"ping"}],"max_tokens":256}'
===========================================

EOF

wait "${ADAPTER_PID}"
