#!/usr/bin/env bash
# Sourced by api.sh — start / wait / stop a local vLLM server (Qwen default chat template).

VLLM_BIN="${VLLM_BIN:-$(command -v vllm || true)}"
VLLM_CONDA_PREFIX="${VLLM_CONDA_PREFIX:-${CONDA_PREFIX:-${VIRTUAL_ENV:-}}}"
VLLM_HOST="${VLLM_HOST:-0.0.0.0}"
VLLM_PORT="${VLLM_PORT:-8007}"
VLLM_GPU_UTIL="${VLLM_GPU_UTIL:-0.90}"
# Empty: do not pass --max-model-len; vLLM uses the model config.
VLLM_MAX_MODEL_LEN="${VLLM_MAX_MODEL_LEN:-}"
# Qwen default template (no custom --chat-template).
VLLM_EXTRA_ARGS="${VLLM_EXTRA_ARGS:---reasoning-parser qwen3 --enable-auto-tool-choice --tool-call-parser qwen3_coder}"
VLLM_READY_TIMEOUT_SEC="${VLLM_READY_TIMEOUT_SEC:-1800}"

VLLM_PID=""
VLLM_LOG=""

_vllm_log() { echo "[vllm $(date '+%F %T')] $*"; }

cleanup_vllm() {
  if [[ -n "${VLLM_PID}" ]] && kill -0 "${VLLM_PID}" 2>/dev/null; then
    _vllm_log "stopping vLLM pid=${VLLM_PID}"
    kill "${VLLM_PID}" 2>/dev/null || true
    for _ in $(seq 1 30); do
      kill -0 "${VLLM_PID}" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "${VLLM_PID}" 2>/dev/null; then
      kill -9 "${VLLM_PID}" 2>/dev/null || true
    fi
    wait "${VLLM_PID}" 2>/dev/null || true
  fi
  VLLM_PID=""
}

wait_vllm_ready() {
  # Health-check against loopback even when VLLM_HOST is 0.0.0.0
  local url="http://127.0.0.1:${VLLM_PORT}/v1/models"
  local deadline=$((SECONDS + VLLM_READY_TIMEOUT_SEC))
  _vllm_log "waiting for vLLM at ${url} (timeout=${VLLM_READY_TIMEOUT_SEC}s)"
  while (( SECONDS < deadline )); do
    if ! kill -0 "${VLLM_PID}" 2>/dev/null; then
      echo "[vllm ERROR] exited early; see log: ${VLLM_LOG}" >&2
      return 1
    fi
    if curl -sf --max-time 2 "${url}" >/dev/null 2>&1; then
      _vllm_log "vLLM is ready"
      return 0
    fi
    sleep 2
  done
  echo "[vllm ERROR] not ready within ${VLLM_READY_TIMEOUT_SEC}s; see log: ${VLLM_LOG}" >&2
  return 1
}

# Usage: start_vllm <model_path> <served_name> <out_dir>
start_vllm() {
  local model_path="$1"
  local served_name="$2"
  local out_dir="$3"

  if [[ -z "${VLLM_BIN}" ]]; then
    echo "[vllm ERROR] vllm not found on PATH; set VLLM_BIN" >&2
    return 1
  fi

  mkdir -p "${out_dir}"
  VLLM_LOG="${out_dir}/vllm_serve.log"

  local -a cmd=(
    "${VLLM_BIN}" serve "${model_path}"
    --host "${VLLM_HOST}"
    --port "${VLLM_PORT}"
    --served-model-name "${served_name}"
    --gpu-memory-utilization "${VLLM_GPU_UTIL}"
    --tensor-parallel-size 1
    --trust-remote-code
  )
  if [[ -n "${VLLM_MAX_MODEL_LEN}" ]]; then
    cmd+=(--max-model-len "${VLLM_MAX_MODEL_LEN}")
  fi
  # shellcheck disable=SC2206
  local -a extra=( ${VLLM_EXTRA_ARGS} )
  cmd+=("${extra[@]}")

  local gpu_vis="${CUDA_VISIBLE_DEVICES:-0}"
  local ld_prefix=""
  if [[ -n "${VLLM_CONDA_PREFIX}" && -d "${VLLM_CONDA_PREFIX}/lib" ]]; then
    ld_prefix="${VLLM_CONDA_PREFIX}/lib"
  fi
  _vllm_log "starting CUDA_VISIBLE_DEVICES=${gpu_vis}: ${model_path} (served-model-name=${served_name})"
  _vllm_log "listen ${VLLM_HOST}:${VLLM_PORT}  log -> ${VLLM_LOG}"
  CUDA_VISIBLE_DEVICES="${gpu_vis}" \
    CONDA_PREFIX="${VLLM_CONDA_PREFIX:-}" \
    LD_LIBRARY_PATH="${ld_prefix}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" \
    "${cmd[@]}" >"${VLLM_LOG}" 2>&1 &
  VLLM_PID=$!
  wait_vllm_ready
}
