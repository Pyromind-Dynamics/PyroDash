#!/usr/bin/env bash
# Python / engine path helpers for run_use only.
#
# Callers: run_use/run_sh/run_coding.sh and the web UI (server.py → run_coding.sh).
# offload/ and evaluation/ do NOT source this file — they consume PYTHON_BIN /
# VLLM_BIN / HARNESS_PYTHON already exported by run_use.
#
# Web UI / CLI must set:
#   VENV_DIR=/path/to/venv_or_conda_env     # SLM / vLLM / adapter
#   HARNESS_PYTHON=/path/to/python         # SWE harness (or conda env root)
#
#   source "${RUN_USE_ROOT}/env_paths.sh"
#   pyrodash_activate_venv "${VENV_DIR}"
#   pyrodash_resolve_harness_python

# shellcheck disable=SC2034
PYRODASH_VENV_DIR="${VENV_DIR:-${PYRODASH_VENV_DIR:-}}"
PYRODASH_BASE_CONDA_PYTHON="${HARNESS_PYTHON:-${PYRODASH_BASE_CONDA_PYTHON:-}}"

pyrodash_activate_venv() {
  local venv_dir="${1:-${PYRODASH_VENV_DIR}}"
  if [[ -z "${venv_dir}" ]]; then
    echo "[env ERROR] VENV_DIR is unset. Set it in the web UI or export VENV_DIR=/path/to/env" >&2
    return 1
  fi
  VENV_DIR="${venv_dir}"
  export VENV_DIR

  if [[ -f "${venv_dir}/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "${venv_dir}/bin/activate"
  elif [[ -x "${venv_dir}/bin/python" || -x "${venv_dir}/bin/python3" ]]; then
    echo "[env] using env prefix (no activate script): ${venv_dir}"
  else
    echo "[env ERROR] VENV_DIR has no bin/python: ${venv_dir}" >&2
    return 1
  fi

  export PATH="${venv_dir}/bin:${PATH}"
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
  export VIRTUAL_ENV="${venv_dir}"
  export PYTHON_BIN="${PYTHON_BIN:-${venv_dir}/bin/python}"
  if [[ ! -x "${PYTHON_BIN}" && -x "${venv_dir}/bin/python3" ]]; then
    PYTHON_BIN="${venv_dir}/bin/python3"
    export PYTHON_BIN
  fi
  export VLLM_BIN="${VLLM_BIN:-${venv_dir}/bin/vllm}"
  export VLLM_CONDA_PREFIX="${VLLM_CONDA_PREFIX:-${venv_dir}}"
  if [[ -x "${PYTHON_BIN}" ]]; then
    export SGLANG_PYTHON="${SGLANG_PYTHON:-${PYTHON_BIN}}"
  fi
  echo "[env] venv=${venv_dir} python=${PYTHON_BIN} vllm=${VLLM_BIN:-missing}"
}

# Normalize HARNESS_PYTHON to an executable (env root → bin/python).
pyrodash_resolve_harness_python() {
  local hp="${HARNESS_PYTHON:-${PYRODASH_BASE_CONDA_PYTHON:-}}"
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
