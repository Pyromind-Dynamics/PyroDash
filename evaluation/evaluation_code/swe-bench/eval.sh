#!/usr/bin/env bash
# SWE-bench Verified against a running offload_code adapter.
# Start the adapter first (offload/offload_code/{tag|entropy}/api.sh), then:
#
#   bash eval.sh --port 18027
#   bash eval.sh --host 10.0.0.1 --port 18027
#
set -euo pipefail
export MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT="${MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT:-3}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${SCRIPT_DIR}/config"
CLUSTER="${CLUSTER:-us}"
case "${CLUSTER}" in
  us|shanghai) ;;
  *) echo "[eval ERROR] CLUSTER must be us|shanghai (got ${CLUSTER})" >&2; exit 1 ;;
esac

# If EVAL_OUTPUT_DIR is set, redirect runs/verified under it (for run_use pipelines).
if [[ -n "${EVAL_OUTPUT_DIR:-}" ]]; then
  EVAL_OUTPUT_DIR="$(cd "${EVAL_OUTPUT_DIR}" 2>/dev/null && pwd || echo "${EVAL_OUTPUT_DIR}")"
  OUT_DIR="${EVAL_OUTPUT_DIR}/runs"
  EVAL_DIR="${EVAL_OUTPUT_DIR}/verified"
else
  OUT_DIR="${SCRIPT_DIR}/output/runs"
  EVAL_DIR="${SCRIPT_DIR}/output/verified"
fi
mkdir -p "${OUT_DIR}" "${EVAL_DIR}"
OUT_DIR="$(cd "${OUT_DIR}" && pwd)"
EVAL_DIR="$(cd "${EVAL_DIR}" && pwd)"

ADAPTER_HOST="${ADAPTER_HOST:-127.0.0.1}"
ADAPTER_PORT="${ADAPTER_PORT:-}"
SUBSET="${SUBSET:-verified}"
SPLIT="${SPLIT:-test}"
WORKERS="${WORKERS:-4}"
STEP_LIMIT="${STEP_LIMIT:-150}"
HARNESS_WORKERS="${HARNESS_WORKERS:-8}"
DATASET_NAME="${DATASET_NAME:-princeton-nlp/SWE-bench_Verified}"
RUN_ID="${RUN_ID:-swebench_offload_pred}"
INSTANCE_FILTER="${INSTANCE_FILTER:-}"
# PYTHON_BIN / HARNESS_PYTHON are provided by run_use (web UI / run_coding.sh).
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || command -v python)}"
if [[ -z "${HARNESS_PYTHON:-}" ]]; then
  echo "[eval ERROR] HARNESS_PYTHON unset. Launch via run_use, or export HARNESS_PYTHON=/path/to/python" >&2
  exit 1
fi
# Accept env root from caller; normalize to bin/python.
if [[ -d "${HARNESS_PYTHON}" && -x "${HARNESS_PYTHON}/bin/python" ]]; then
  HARNESS_PYTHON="${HARNESS_PYTHON}/bin/python"
elif [[ -d "${HARNESS_PYTHON}" && -x "${HARNESS_PYTHON}/bin/python3" ]]; then
  HARNESS_PYTHON="${HARNESS_PYTHON}/bin/python3"
fi
if [[ ! -x "${HARNESS_PYTHON}" ]]; then
  echo "[eval ERROR] HARNESS_PYTHON not executable: ${HARNESS_PYTHON}" >&2
  exit 1
fi
export HARNESS_PYTHON
echo "[eval] HARNESS_PYTHON=${HARNESS_PYTHON}"

usage() {
  cat <<EOF
Usage: bash eval.sh --port PORT [--host HOST]

Requires a running offload adapter (GET /health).

Options:
  --host HOST          Adapter host (default: ${ADAPTER_HOST} or ADAPTER_HOST)
  --port PORT          Adapter port (required; or set ADAPTER_PORT)
  -h, --help           Show this help

Env overrides:
  EVAL_OUTPUT_DIR      if set, write runs/ and verified/ under this directory
  MINI_EXTRA_ARGS      extra mini-extra argv, one flag per line. When set, replaces
                       SUBSET / SPLIT / WORKERS / STEP_LIMIT / pull_timeout.
                       --filter or --slice here also replaces INSTANCE_FILTER.
                       -o / --output is ignored; output dir stays fixed.
  INSTANCE_FILTER      if set, pass --filter to mini-extra (e.g. swe_20filter ids)
  SUBSET               mini-extra subset (default: verified)
  SPLIT                mini-extra split (default: test)
  WORKERS              mini-extra -w (default: 4)
  STEP_LIMIT           agent.step_limit (default: 150)
  HARNESS_WORKERS      harness --max_workers (default: 8)
  DATASET_NAME         harness dataset (default: princeton-nlp/SWE-bench_Verified)
  RUN_ID               harness run id
  PYTHON_BIN           python for helper bits
  HARNESS_PYTHON       python with swebench+docker (required; set by run_use / web UI)
  CLUSTER              us (default) | shanghai
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      ADAPTER_HOST="$2"
      shift 2
      ;;
    --port)
      ADAPTER_PORT="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "${ADAPTER_PORT}" ]]; then
  echo "[eval ERROR] --port (or ADAPTER_PORT) is required" >&2
  usage >&2
  exit 1
fi

ADAPTER_BASE="http://${ADAPTER_HOST}:${ADAPTER_PORT}"
# OpenAI chat.completions base (litellm appends /chat/completions)
API_BASE="${ADAPTER_BASE}/v1"
HEALTH_URL="${ADAPTER_BASE}/health"

echo "[eval] checking ${HEALTH_URL}"
if ! curl -sf --max-time 5 "${HEALTH_URL}" >/dev/null; then
  echo "[eval ERROR] adapter not ready at ${ADAPTER_BASE}" >&2
  echo "  Start offload first, e.g.:" >&2
  echo "    ADAPTER_PORT=${ADAPTER_PORT} bash offload/offload_code/tag/api.sh" >&2
  exit 1
fi
echo "[eval] adapter ready (OpenAI api_base=${API_BASE})"

MODEL_YAML="${OUT_DIR}/model.${ADAPTER_HOST}.${ADAPTER_PORT}.yaml"
sed "s|__API_BASE__|${API_BASE}|g" "${CONFIG_DIR}/model.yaml.template" >"${MODEL_YAML}"
# Ensure registry path is absolute for mini-extra
REGISTRY_ABS="${CONFIG_DIR}/registry.json"

FILTER_ARGS=()
if [[ -n "${INSTANCE_FILTER}" ]]; then
  FILTER_ARGS+=(--filter "${INSTANCE_FILTER}")
  echo "[eval] INSTANCE_FILTER=${INSTANCE_FILTER}"
fi

ENV_TESTBED_YAML="${CONFIG_DIR}/env_testbed_path.yaml"
echo "[eval] CLUSTER=${CLUSTER}"
echo "[eval] mini-extra swebench → ${OUT_DIR}"
echo "[eval] env overlay: ${ENV_TESTBED_YAML}"

MINI_ARGS=(
  -c swebench.yaml
  -c "${MODEL_YAML}"
  -c "${ENV_TESTBED_YAML}"
  -c "model.litellm_model_registry=${REGISTRY_ABS}"
)

USER_MINI=()
_mini_extra="${MINI_EXTRA_ARGS:-}"
if [[ -n "${_mini_extra//[[:space:]]/}" ]]; then
  _argfile="$(mktemp)"
  "${PYTHON_BIN}" -c 'import os, shlex, sys
args = shlex.split(os.environ.get("MINI_EXTRA_ARGS", ""))
data = b"\0".join(arg.encode() for arg in args)
if args:
    data += b"\0"
sys.stdout.buffer.write(data)
' >"${_argfile}"
  while IFS= read -r -d '' _arg; do
    [[ -n "${_arg}" ]] || continue
    USER_MINI+=("${_arg}")
  done < "${_argfile}"
  rm -f "${_argfile}"
  KEPT_MINI=()
  _skip_next=0
  for _arg in "${USER_MINI[@]}"; do
    if [[ "${_skip_next}" == "1" ]]; then
      _skip_next=0
      echo "[eval] ignoring user output path: ${_arg}"
      continue
    fi
    case "${_arg}" in
      -o|--output)
        _skip_next=1
        echo "[eval] ignoring user ${_arg} (output dir is fixed at ${OUT_DIR})"
        continue
        ;;
      --output=*)
        echo "[eval] ignoring user ${_arg} (output dir is fixed at ${OUT_DIR})"
        continue
        ;;
    esac
    KEPT_MINI+=("${_arg}")
  done
  MINI_ARGS+=("${KEPT_MINI[@]}")
  _user_has_selector=0
  for _arg in "${KEPT_MINI[@]}"; do
    case "${_arg}" in
      --filter|--slice|--filter=*|--slice=*) _user_has_selector=1 ;;
    esac
  done
  if [[ "${_user_has_selector}" == "0" && ${#FILTER_ARGS[@]} -gt 0 ]]; then
    MINI_ARGS+=("${FILTER_ARGS[@]}")
    echo "[eval] MINI_EXTRA_ARGS has no --filter/--slice; still applying INSTANCE_FILTER"
  fi
  echo "[eval] using MINI_EXTRA_ARGS (SUBSET/SPLIT/WORKERS/STEP_LIMIT defaults skipped)"
else
  MINI_ARGS+=(
    -c "environment.pull_timeout=7200"
    -c "agent.step_limit=${STEP_LIMIT}"
    --subset "${SUBSET}"
    --split "${SPLIT}"
    "${FILTER_ARGS[@]}"
    -w "${WORKERS}"
  )
fi
MINI_ARGS+=(-o "${OUT_DIR}")
echo "[eval] mini-extra argv:"
printf '  %q\n' "${MINI_ARGS[@]}"

if [[ "${CLUSTER}" == "shanghai" ]]; then
  # Aliyun images + docker-rt. Keep bash -lc (do not install docker_rt_testbed_exec.sh).
  export DOCKER_HOST="${DOCKER_HOST:-unix:///tmp/docker-rt.sock}"
  export MSWEA_NO_DOCKER_WRAPPER=1
  unset MSWEA_DOCKER_EXECUTABLE
  export SWEBENCH_DOCKER_IMAGE_PREFIX="${SWEBENCH_DOCKER_IMAGE_PREFIX:-pyromind-registry-vpc.cn-shanghai.cr.aliyuncs.com/pyromind}"
  export SWEBENCH_DOCKER_NAMESPACE="${SWEBENCH_DOCKER_NAMESPACE:-${SWEBENCH_DOCKER_IMAGE_PREFIX}}"
  export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
  export HF_DATASETS_OFFLINE="${HF_DATASETS_OFFLINE:-1}"
  export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
  export LITELLM_LOCAL_MODEL_COST_MAP="${LITELLM_LOCAL_MODEL_COST_MAP:-True}"
  export SWEBENCH_GITHUB_CACHE="${SWEBENCH_GITHUB_CACHE:-${SCRIPT_DIR}/cache/github_raw}"
  export SWEBENCH_GITHUB_RAW_MIRRORS="${SWEBENCH_GITHUB_RAW_MIRRORS:-https://ghproxy.net/}"
  export SWEBENCH_GITHUB_RAW_TIMEOUT="${SWEBENCH_GITHUB_RAW_TIMEOUT:-30}"
  mkdir -p "${SWEBENCH_GITHUB_CACHE}"
  echo "[eval] shanghai image prefix=${SWEBENCH_DOCKER_IMAGE_PREFIX}"
  echo "[eval] DOCKER_HOST=${DOCKER_HOST} MSWEA_DOCKER_EXECUTABLE=${MSWEA_DOCKER_EXECUTABLE:-<unset>}"

  MINI_EXTRA_BIN="$(command -v mini-extra || true)"
  MINI_EXTRA_PYTHON=""
  if [[ -n "${MINI_EXTRA_BIN}" && -f "${MINI_EXTRA_BIN}" ]]; then
    _shebang="$(head -n 1 "${MINI_EXTRA_BIN}")"
    if [[ "${_shebang}" == "#!"* ]]; then
      MINI_EXTRA_PYTHON="${_shebang#\#!}"
    fi
  fi
  MINI_EXTRA_PYTHON="${MINI_EXTRA_PYTHON:-${PYTHON_BIN}}"
  "${MINI_EXTRA_PYTHON}" "${SCRIPT_DIR}/mini_extra_shanghai.py" "${MINI_ARGS[@]}"
else
  mini-extra swebench "${MINI_ARGS[@]}"
fi

PREDS="${OUT_DIR}/preds.json"
[[ -f "${PREDS}" ]] || { echo "[eval ERROR] missing ${PREDS}" >&2; exit 1; }

echo "[eval] harness → ${EVAL_DIR}  (python=${HARNESS_PYTHON})"
if ! "${HARNESS_PYTHON}" -c "import docker, swebench" >/dev/null 2>&1; then
  echo "[eval ERROR] HARNESS_PYTHON missing packages: need 'docker' and 'swebench'" >&2
  echo "  tried: ${HARNESS_PYTHON}" >&2
  echo "  Note: Docker CLI can exist while the Python 'docker' SDK is missing." >&2
  echo "  Fix:  pip install docker swebench   OR set HARNESS_PYTHON to an env that has them" >&2
  exit 1
fi
# swebench 4.x ignores --report_dir and writes <model>.<run_id>.json + logs/run_evaluation/
# to CWD. Run inside EVAL_DIR so all harness outputs stay under output/<run>/.../verified/.
mkdir -p "${EVAL_DIR}"
(
  cd "${EVAL_DIR}"
  "${HARNESS_PYTHON}" "${SCRIPT_DIR}/run_harness.py" \
    --dataset_name "${DATASET_NAME}" \
    --predictions_path "${PREDS}" \
    --max_workers "${HARNESS_WORKERS}" \
    --run_id "${RUN_ID}" \
    --report_dir "${EVAL_DIR}" \
    --cache_level instance \
    --clean False
)

REPORT_GLOB="*.${RUN_ID}.json"
for cand in \
  "./${REPORT_GLOB}" \
  "${OUT_DIR}/${REPORT_GLOB}" \
  "${EVAL_DIR}/${REPORT_GLOB}"
do
  # shellcheck disable=SC2086
  for f in ${cand}; do
    [[ -f "${f}" ]] || continue
    base="$(basename "${f}")"
    if [[ "$(cd "$(dirname "${f}")" && pwd)/${base}" != "${EVAL_DIR}/${base}" ]]; then
      mv -f "${f}" "${EVAL_DIR}/${base}"
      echo "[eval] moved harness report → ${EVAL_DIR}/${base}"
    else
      echo "[eval] harness report → ${f}"
    fi
  done
done

echo "[eval] done"
echo "[eval] preds : ${PREDS}"
echo "[eval] report: ${EVAL_DIR}"
echo "[eval] stats : GET ${ADAPTER_BASE}/stats"
