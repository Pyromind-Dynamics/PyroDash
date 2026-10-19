#!/usr/bin/env bash
# Canonical Python / engine paths for PyroDash.
#
#   Project .venv  → vLLM / SGLang / adapter / run_use pipeline
#   Base conda     → SWE-bench harness only (needs swebench + docker SDK)
#
# Source from other scripts:
#   source "${PYRODASH_ROOT}/env_paths.sh"
#   pyrodash_activate_venv
#   pyrodash_resolve_harness_python
#
# Do not use conda env gui-360.

# shellcheck disable=SC2034
PYRODASH_VENV_DIR="${VENV_DIR:-${PYRODASH_VENV_DIR:-/workspace/work/mjy/.venv}}"
PYRODASH_BASE_CONDA_PYTHON="${PYRODASH_BASE_CONDA_PYTHON:-/workspace/.conda/bin/python}"

pyrodash_activate_venv() {
  local venv_dir="${1:-${PYRODASH_VENV_DIR}}"
  VENV_DIR="${venv_dir}"
  export VENV_DIR
  if [[ -f "${venv_dir}/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "${venv_dir}/bin/activate"
    export PATH="${venv_dir}/bin:${PATH}"
    export VIRTUAL_ENV="${venv_dir}"
    export PYTHON_BIN="${PYTHON_BIN:-${venv_dir}/bin/python}"
    export VLLM_BIN="${VLLM_BIN:-${venv_dir}/bin/vllm}"
    export VLLM_CONDA_PREFIX="${VLLM_CONDA_PREFIX:-${venv_dir}}"
    if [[ -x "${venv_dir}/bin/python" ]]; then
      export SGLANG_PYTHON="${SGLANG_PYTHON:-${venv_dir}/bin/python}"
    fi
    echo "[env] venv=${venv_dir} python=${PYTHON_BIN} vllm=${VLLM_BIN:-missing}"
  else
    echo "[env WARN] venv not found: ${venv_dir}" >&2
    export PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || command -v python || true)}"
  fi
  if [[ -n "${PYTHON_BIN:-}" && -x "${PYTHON_BIN}" ]]; then
    :
  else
    PYTHON_BIN="$(command -v python3 || command -v python || true)"
    export PYTHON_BIN
  fi
}

# Sets HARNESS_PYTHON to base conda if it has docker+swebench.
pyrodash_resolve_harness_python() {
  if [[ -n "${HARNESS_PYTHON:-}" && -x "${HARNESS_PYTHON}" ]]; then
    if "${HARNESS_PYTHON}" -c "import docker, swebench" >/dev/null 2>&1; then
      export HARNESS_PYTHON
      return 0
    fi
  fi
  local cand
  for cand in \
    "${PYRODASH_BASE_CONDA_PYTHON}" \
    /workspace/.conda/bin/python \
    /workspace/.conda/bin/python3
  do
    [[ -x "${cand}" ]] || continue
    if "${cand}" -c "import docker, swebench" >/dev/null 2>&1; then
      HARNESS_PYTHON="${cand}"
      export HARNESS_PYTHON
      return 0
    fi
  done
  # Last resort: caller PYTHON_BIN (may lack swebench).
  HARNESS_PYTHON="${PYTHON_BIN:-$(command -v python3 || command -v python || true)}"
  export HARNESS_PYTHON
  return 1
}
