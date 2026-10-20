#!/usr/bin/env bash
# 改环境只改下面两行。启动时 export，或网页里填写，会覆盖这里。
#
# VLLM_ENV        小模型 / adapter 的环境根目录（里面要有 bin/python、bin/vllm）
# HARNESS_PYTHON  SWE 打分用的 python，填 bin/python 或环境根目录都行

VLLM_ENV="${VLLM_ENV:-/workspace/work/mjy/.venv}"
HARNESS_PYTHON="${HARNESS_PYTHON:-/workspace/.conda/bin/python}"

# 把 VLLM_ENV 变成当前 python，并导出 PYTHON_BIN / VLLM_BIN。
pyrodash_activate_vllm_env() {
  local vllm_env="${1:-${VLLM_ENV}}"
  if [[ ! -x "${vllm_env}/bin/python" && ! -x "${vllm_env}/bin/python3" ]]; then
    echo "[env ERROR] VLLM_ENV 里没有 bin/python: ${vllm_env}" >&2
    return 1
  fi
  VLLM_ENV="${vllm_env}"
  if [[ -f "${vllm_env}/bin/activate" ]]; then
    # shellcheck disable=SC1091
    source "${vllm_env}/bin/activate"
  fi
  if [[ -x "${vllm_env}/bin/python" ]]; then
    PYTHON_BIN="${vllm_env}/bin/python"
  else
    PYTHON_BIN="${vllm_env}/bin/python3"
  fi
  export VLLM_ENV PYTHON_BIN
  export PATH="${vllm_env}/bin:${PATH}"
  export VIRTUAL_ENV="${vllm_env}"
  export VLLM_BIN="${vllm_env}/bin/vllm"
  export VLLM_CONDA_PREFIX="${vllm_env}"
  export SGLANG_PYTHON="${PYTHON_BIN}"
  echo "[env] vllm=${vllm_env} python=${PYTHON_BIN}"
}

# 把 HARNESS_PYTHON 收成可执行文件，并把它的 bin 放进 PATH（mini-extra 在这里）。
pyrodash_resolve_harness_python() {
  local hp="${HARNESS_PYTHON:-}"
  if [[ -z "${hp}" ]]; then
    echo "[env ERROR] HARNESS_PYTHON 是空的" >&2
    return 1
  fi
  if [[ -d "${hp}" && -x "${hp}/bin/python" ]]; then
    hp="${hp}/bin/python"
  elif [[ -d "${hp}" && -x "${hp}/bin/python3" ]]; then
    hp="${hp}/bin/python3"
  fi
  if [[ ! -x "${hp}" ]]; then
    echo "[env ERROR] HARNESS_PYTHON 不可执行: ${hp}" >&2
    return 1
  fi
  HARNESS_PYTHON="${hp}"
  export HARNESS_PYTHON
  export PATH="$(dirname "${hp}"):${PATH}"
  echo "[env] harness=${HARNESS_PYTHON}"
}
