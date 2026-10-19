#!/usr/bin/env bash
# Start math offload adapter (SLM /completions + bare <|llm_offload|> + LLM relay).
# Ctrl+C stops adapter (+ local vLLM if started).
#
# SLM can be:
#   A) local weights  — set MODEL_PATH (directory); this script starts vLLM
#   B) remote API     — set SLM_BASE_URL + SLM_MODEL (+ SLM_API_KEY); still need
#                       TOKENIZER_PATH or MODEL_PATH for chat template
set -euo pipefail

OFFLOAD_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYRODASH_ROOT="$(cd "${OFFLOAD_ROOT}/../.." && pwd)"
# Prefer project .venv for adapter / vLLM.
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

MODEL_PATH="${MODEL_PATH:-}"
TOKENIZER_PATH="${TOKENIZER_PATH:-}"
SLM_BASE_URL="${SLM_BASE_URL:-}"
SLM_API_KEY="${SLM_API_KEY:-dummy}"
SLM_MODEL="${SLM_MODEL:-}"

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

LLM_BASE_URL="${LLM_BASE_URL:-https://your-llm-host/v1}"
LLM_API_KEY="${LLM_API_KEY:-your-llm-api-key}"
LLM_MODEL="${LLM_MODEL:-your-llm-model}"

VLLM_HOST="${VLLM_HOST:-0.0.0.0}"
VLLM_PORT="${VLLM_PORT:-8001}"
ADAPTER_HOST="${ADAPTER_HOST:-0.0.0.0}"
ADAPTER_PORT="${ADAPTER_PORT:-18031}"

SLM_TEMPERATURE="${SLM_TEMPERATURE:-0.1}"
LLM_TEMPERATURE="${LLM_TEMPERATURE:-1.0}"
LLM_TOP_P="${LLM_TOP_P:-1.0}"

MAX_NEW_TOKENS="${MAX_NEW_TOKENS:-8192}"
# Math eval historically used 40960; empty = model default.
MAX_MODEL_LEN="${MAX_MODEL_LEN:-40960}"

# USE_LLM=false → SLM-only (no relay)
USE_LLM="${USE_LLM:-true}"
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

if [[ -z "${TOKENIZER_PATH}" ]]; then
  if [[ -n "${MODEL_PATH}" && -d "${MODEL_PATH}" ]]; then
    TOKENIZER_PATH="${MODEL_PATH}"
  else
    echo "ERROR: TOKENIZER_PATH (or MODEL_PATH) required for chat template / vocab" >&2
    exit 1
  fi
fi
[[ -d "${TOKENIZER_PATH}" ]] || { echo "ERROR: TOKENIZER_PATH missing: ${TOKENIZER_PATH}" >&2; exit 1; }

case "${USE_LLM}" in
  true|True|TRUE|1|yes|YES) USE_LLM=true ;;
  false|False|FALSE|0|no|NO) USE_LLM=false ;;
  *) echo "ERROR: USE_LLM must be true or false (got ${USE_LLM})" >&2; exit 1 ;;
esac
if [[ "${USE_LLM}" == "true" ]]; then
  [[ -n "${LLM_API_KEY}" && "${LLM_API_KEY}" != "your-llm-api-key" ]] || \
    echo "WARNING: set LLM_API_KEY before production use" >&2
else
  LLM_BASE_URL="${LLM_BASE_URL:-http://127.0.0.1:0/v1}"
  LLM_API_KEY="${LLM_API_KEY:-unused}"
  LLM_MODEL="${LLM_MODEL:-unused}"
  echo "[api] USE_LLM=false → SLM-only (no LLM relay)"
fi

RUN_STAMP="$(date '+%Y%m%d_%H%M%S')"
SAFE_NAME="$(echo "${SERVED_NAME}" | tr '/: ' '___')"
LOG_DIR="${OFFLOAD_LOG_DIR:-${OFFLOAD_ROOT}/logs/${SAFE_NAME}_${RUN_STAMP}}"
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
  echo "[adapter] tokenizer=${TOKENIZER_PATH}"
  echo "[adapter] SLM=${SLM_MODEL} @ ${SLM_BASE_URL}"
  echo "[adapter] LLM=${LLM_MODEL} @ ${LLM_BASE_URL}  use_llm=${USE_LLM}"
  echo "[adapter] listen ${ADAPTER_HOST}:${ADAPTER_PORT}  log=${ADAPTER_LOG}"
  echo "[adapter] stats -> ${LOG_DIR}/adapter_stats"
  "${PYTHON_BIN}" \
    "${OFFLOAD_ROOT}/serve_adapter.py" \
    --host "${ADAPTER_HOST}" \
    --port "${ADAPTER_PORT}" \
    --tokenizer-path "${TOKENIZER_PATH}" \
    --slm-base-url "${SLM_BASE_URL}" \
    --slm-api-key "${SLM_API_KEY}" \
    --slm-model "${SLM_MODEL}" \
    --llm-base-url "${LLM_BASE_URL}" \
    --llm-api-key "${LLM_API_KEY}" \
    --llm-model "${LLM_MODEL}" \
    --use-llm "${USE_LLM}" \
    --max-new-tokens "${MAX_NEW_TOKENS}" \
    --slm-temperature "${SLM_TEMPERATURE}" \
    --llm-temperature "${LLM_TEMPERATURE}" \
    --llm-top-p "${LLM_TOP_P}" \
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

========== Math offload API ready ==========
  adapter health : http://${HOST_IP}:${ADAPTER_PORT}/health
  math complete  : POST http://${HOST_IP}:${ADAPTER_PORT}/v1/math/complete
  adapter stats  : http://${HOST_IP}:${ADAPTER_PORT}/stats
${SLM_LINE}
  LLM            : ${LLM_MODEL} @ ${LLM_BASE_URL}  (use_llm=${USE_LLM})
  offload tag    : <|llm_offload|>
  token stats    : ${LOG_DIR}/adapter_stats/
  logs           : ${LOG_DIR}/
  Ctrl+C to stop

curl -sS http://${HOST_IP}:${ADAPTER_PORT}/v1/math/complete \\
  -H 'Content-Type: application/json' \\
  -d '{"question":"1+1=?","max_tokens":256}'
============================================

EOF

wait "${ADAPTER_PID}"
