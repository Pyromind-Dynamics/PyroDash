#!/usr/bin/env bash
# Python / engine path helpers for run_use only.
#
# Callers: run_use/run_sh/run_coding.sh and the web UI (server.py → run_coding.sh).
# offload/ and evaluation/ do NOT source this file — they consume PYTHON_BIN /
# VLLM_BIN / HARNESS_PYTHON already exported by run_use.
#
# Web UI / CLI must set:
#   VLLM_ENV=/path/to/vllm_conda_env        # vLLM / SLM / adapter
#   HARNESS_PYTHON=/path/to/python          # SWE harness (or conda env root)
#
#   source "${RUN_USE_ROOT}/env_paths.sh"
#   pyrodash_activate_vllm_env "${VLLM_ENV}"
#   pyrodash_resolve_harness_python

# shellcheck disable=SC2034
VLLM_ENV="${VLLM_ENV:-}"
HARNESS_PYTHON="${HARNESS_PYTHON:-}"

pyrodash_activate_vllm_env() {
  local vllm_env="${1:-${VLLM_ENV}}"
  if [[ -z "${vllm_env}" ]]; then
    echo "[env ERROR] VLLM_ENV is unset. Set it in the web UI or export VLLM_ENV=/path/to/vllm_env" >&2
    return 1
  fi
  VLLM_ENV="${vllm_env}"
  export VLLM_ENV

  if [[ -f "${vllm_env}/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "${vllm_env}/bin/activate"
  elif [[ -x "${vllm_env}/bin/python" || -x "${vllm_env}/bin/python3" ]]; then
    echo "[env] using vLLM env prefix (no activate script): ${vllm_env}"
  else
    echo "[env ERROR] VLLM_ENV has no bin/python: ${vllm_env}" >&2
    return 1
  fi

  export PATH="${vllm_env}/bin:${PATH}"
  if [[ -n "${HARNESS_PYTHON:-}" ]]; then
    local hp="${HARNESS_PYTHON}"
    if [[ -d "${hp}" && -x "${hp}/bin/python" ]]; then
      hp="${hp}/bin/python"
    elif [[ -d "${hp}" && -x "${hp}/bin/python3" ]]; then
      hp="${hp}/bin/python3"
    fi
    if [[ -x "${hp}" ]]; then
      export PATH="$(dirname "${hp}"):${PATH}"
    fi
  fi
  export VIRTUAL_ENV="${vllm_env}"
  export PYTHON_BIN="${PYTHON_BIN:-${vllm_env}/bin/python}"
  if [[ ! -x "${PYTHON_BIN}" && -x "${vllm_env}/bin/python3" ]]; then
    PYTHON_BIN="${vllm_env}/bin/python3"
    export PYTHON_BIN
  fi
  export VLLM_BIN="${VLLM_BIN:-${vllm_env}/bin/vllm}"
  export VLLM_CONDA_PREFIX="${VLLM_CONDA_PREFIX:-${vllm_env}}"
  if [[ -x "${PYTHON_BIN}" ]]; then
    export SGLANG_PYTHON="${SGLANG_PYTHON:-${PYTHON_BIN}}"
  fi
  echo "[env] vllm_env=${vllm_env} python=${PYTHON_BIN} vllm=${VLLM_BIN:-missing}"
}

# Normalize HARNESS_PYTHON to an executable (env root → bin/python).
pyrodash_resolve_harness_python() {
  local hp="${HARNESS_PYTHON:-}"
  if [[ -z "${hp}" ]]; then
    echo "[env ERROR] HARNESS_PYTHON is unset. Set it in the web UI or export HARNESS_PYTHON=/path/to/python" >&2
    return 1
  fi
  if [[ -d "${hp}" && -x "${hp}/bin/python" ]]; then
    hp="${hp}/bin/python"
  elif [[ -d "${hp}" && -x "${hp}/bin/python3" ]]; then
    hp="${hp}/bin/python3"
  fi
  if [[ ! -x "${hp}" ]]; then
    echo "[env ERROR] HARNESS_PYTHON not executable: ${hp}" >&2
    HARNESS_PYTHON="${hp}"
    export HARNESS_PYTHON
    return 1
  fi
  HARNESS_PYTHON="${hp}"
  export HARNESS_PYTHON
  if ! "${HARNESS_PYTHON}" -c "import docker, swebench" >/dev/null 2>&1; then
    echo "[env WARN] HARNESS_PYTHON missing docker/swebench: ${HARNESS_PYTHON}" >&2
    return 1
  fi
  return 0
}
