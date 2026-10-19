#!/usr/bin/env bash
# Sourced by api.sh — start / wait / stop a local vLLM server (Qwen default + max-logprobs for entropy).

VLLM_BIN="${VLLM_BIN:-$(command -v vllm || true)}"
VLLM_CONDA_PREFIX="${VLLM_CONDA_PREFIX:-${CONDA_PREFIX:-${VIRTUAL_ENV:-}}}"
VLLM_HOST="${VLLM_HOST:-${SLM_HOST:-0.0.0.0}}"
VLLM_PORT="${SLM_PORT:-${VLLM_PORT:-8008}}"
# Must be >= ENTROPY_TOP_K so thinking-token top-k logprobs are returned.
VLLM_MAX_LOGPROBS="${VLLM_MAX_LOGPROBS:-20}"
# Editable CLI flags (UI / env). Appended as-is after host/port/model.
# Add e.g. --max-model-len 128000 here when needed.
if [[ ! -v VLLM_EXTRA_ARGS ]]; then
  VLLM_EXTRA_ARGS="--gpu-memory-utilization 0.90 --tensor-parallel-size 1 --trust-remote-code --max-logprobs ${VLLM_MAX_LOGPROBS} --reasoning-parser qwen3 --enable-auto-tool-choice --tool-call-parser qwen3_coder"
fi
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
  ln -sfn "vllm_serve.log" "${out_dir}/slm_serve.log"

  local -a cmd=(
    "${VLLM_BIN}" serve "${model_path}"
    --host "${VLLM_HOST}"
    --port "${VLLM_PORT}"
    --served-model-name "${served_name}"
  )
  # shellcheck disable=SC2206
  local -a extra=( ${VLLM_EXTRA_ARGS} )
  if ((${#extra[@]})); then
    cmd+=("${extra[@]}")
  fi

  local gpu_vis="${CUDA_VISIBLE_DEVICES:-0}"
  local ld_prefix=""
  if [[ -n "${VLLM_CONDA_PREFIX}" && -d "${VLLM_CONDA_PREFIX}/lib" ]]; then
    ld_prefix="${VLLM_CONDA_PREFIX}/lib"
  fi
  _vllm_log "starting CUDA_VISIBLE_DEVICES=${gpu_vis}: ${model_path} (served-model-name=${served_name})"
  _vllm_log "listen ${VLLM_HOST}:${VLLM_PORT}  log -> ${VLLM_LOG}"
  _vllm_log "extra: ${VLLM_EXTRA_ARGS}"
  CUDA_VISIBLE_DEVICES="${gpu_vis}" \
    CONDA_PREFIX="${VLLM_CONDA_PREFIX:-}" \
    LD_LIBRARY_PATH="${ld_prefix}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}" \
    "${cmd[@]}" >"${VLLM_LOG}" 2>&1 &
  VLLM_PID=$!
  wait_vllm_ready
}
