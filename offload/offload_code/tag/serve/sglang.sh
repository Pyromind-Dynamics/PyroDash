#!/usr/bin/env bash
# Sourced by api.sh — start / wait / stop a local SGLang OpenAI-compatible server.

SGLANG_BIN="${SGLANG_BIN:-}"
if [[ -z "${SGLANG_BIN}" ]]; then
  if command -v sglang >/dev/null 2>&1; then
    SGLANG_BIN="$(command -v sglang)"
  else
    SGLANG_BIN=""
  fi
fi
SGLANG_PYTHON="${SGLANG_PYTHON:-${PYTHON_BIN:-$(command -v python3 || command -v python || true)}}"
SGLANG_HOST="${SGLANG_HOST:-${SLM_HOST:-${VLLM_HOST:-0.0.0.0}}}"
SGLANG_PORT="${SGLANG_PORT:-${SLM_PORT:-${VLLM_PORT:-8007}}}"
# Editable CLI flags (UI / env). Appended as-is after host/port/model.
# Add e.g. --context-length 128000 here when needed.
if [[ ! -v SGLANG_EXTRA_ARGS ]]; then
  SGLANG_EXTRA_ARGS="--tp 1 --mem-fraction-static 0.90 --tool-call-parser qwen3_coder --reasoning-parser qwen3"
fi
SGLANG_READY_TIMEOUT_SEC="${SGLANG_READY_TIMEOUT_SEC:-1800}"

SGLANG_PID=""
SGLANG_LOG=""

_sglang_log() { echo "[sglang $(date '+%F %T')] $*"; }

cleanup_sglang() {
  if [[ -n "${SGLANG_PID}" ]] && kill -0 "${SGLANG_PID}" 2>/dev/null; then
    _sglang_log "stopping SGLang pid=${SGLANG_PID}"
    kill "${SGLANG_PID}" 2>/dev/null || true
    for _ in $(seq 1 30); do
      kill -0 "${SGLANG_PID}" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "${SGLANG_PID}" 2>/dev/null; then
      kill -9 "${SGLANG_PID}" 2>/dev/null || true
    fi
    wait "${SGLANG_PID}" 2>/dev/null || true
  fi
  SGLANG_PID=""
}

wait_sglang_ready() {
  local url="http://127.0.0.1:${SGLANG_PORT}/v1/models"
  local deadline=$((SECONDS + SGLANG_READY_TIMEOUT_SEC))
  _sglang_log "waiting for SGLang at ${url} (timeout=${SGLANG_READY_TIMEOUT_SEC}s)"
  while (( SECONDS < deadline )); do
    if ! kill -0 "${SGLANG_PID}" 2>/dev/null; then
      echo "[sglang ERROR] exited early; see log: ${SGLANG_LOG}" >&2
      return 1
    fi
    if curl -sf --max-time 2 "${url}" >/dev/null 2>&1; then
      _sglang_log "SGLang is ready"
      return 0
    fi
    sleep 2
  done
  echo "[sglang ERROR] not ready within ${SGLANG_READY_TIMEOUT_SEC}s; see log: ${SGLANG_LOG}" >&2
  return 1
}

# Usage: start_sglang <model_path> <served_name> <out_dir>
start_sglang() {
  local model_path="$1"
  local served_name="$2"
  local out_dir="$3"

  mkdir -p "${out_dir}"
  SGLANG_LOG="${out_dir}/sglang_serve.log"
  ln -sfn "sglang_serve.log" "${out_dir}/slm_serve.log"

  local -a cmd=()
  if [[ -n "${SGLANG_BIN}" && "${SGLANG_BIN}" == *launch_server* ]]; then
    # shellcheck disable=SC2206
    cmd=( ${SGLANG_BIN} )
  elif [[ -n "${SGLANG_BIN}" ]]; then
    cmd=("${SGLANG_BIN}" launch_server)
  elif [[ -n "${SGLANG_PYTHON}" ]]; then
    cmd=("${SGLANG_PYTHON}" -m sglang.launch_server)
  else
    echo "[sglang ERROR] sglang not found; set SGLANG_BIN or SGLANG_PYTHON" >&2
    return 1
  fi

  cmd+=(
    --model-path "${model_path}"
    --host "${SGLANG_HOST}"
    --port "${SGLANG_PORT}"
    --served-model-name "${served_name}"
  )
  # shellcheck disable=SC2206
  local -a extra=( ${SGLANG_EXTRA_ARGS} )
  if ((${#extra[@]})); then
    cmd+=("${extra[@]}")
  fi

  local gpu_vis="${CUDA_VISIBLE_DEVICES:-0}"
  _sglang_log "starting CUDA_VISIBLE_DEVICES=${gpu_vis}: ${model_path} (served-model-name=${served_name})"
  _sglang_log "listen ${SGLANG_HOST}:${SGLANG_PORT}  log -> ${SGLANG_LOG}"
  _sglang_log "extra: ${SGLANG_EXTRA_ARGS}"
  _sglang_log "cmd: ${cmd[*]}"
  CUDA_VISIBLE_DEVICES="${gpu_vis}" \
    "${cmd[@]}" >"${SGLANG_LOG}" 2>&1 &
  SGLANG_PID=$!
  wait_sglang_ready
}
