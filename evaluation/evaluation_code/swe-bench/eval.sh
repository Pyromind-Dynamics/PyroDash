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
PYRODASH_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
# shellcheck disable=SC1091
source "${PYRODASH_ROOT}/env_paths.sh"

# If EVAL_OUTPUT_DIR is set, redirect runs/verified under it (for run_use pipelines).
if [[ -n "${EVAL_OUTPUT_DIR:-}" ]]; then
  OUT_DIR="${EVAL_OUTPUT_DIR}/runs"
  EVAL_DIR="${EVAL_OUTPUT_DIR}/verified"
else
  OUT_DIR="${SCRIPT_DIR}/output/runs"
  EVAL_DIR="${SCRIPT_DIR}/output/verified"
fi
mkdir -p "${OUT_DIR}" "${EVAL_DIR}"

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
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || command -v python)}"
# Harness: base conda (swebench 5.x). Project .venv is for vLLM only.
pyrodash_resolve_harness_python || true
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
  INSTANCE_FILTER      if set, pass --filter to mini-extra (e.g. swe_20filter ids)
  SUBSET               mini-extra subset (default: verified)
  SPLIT                mini-extra split (default: test)
  WORKERS              mini-extra -w (default: 4)
  STEP_LIMIT           agent.step_limit (default: 150)
  HARNESS_WORKERS      harness --max_workers (default: 8)
  DATASET_NAME         harness dataset (default: princeton-nlp/SWE-bench_Verified)
  RUN_ID               harness run id
  PYTHON_BIN           python for helper bits
  HARNESS_PYTHON       python with swebench+docker (default: base conda via env_paths.sh)
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
echo "[eval] mini-extra swebench → ${OUT_DIR}"
echo "[eval] env overlay: ${ENV_TESTBED_YAML}"
mini-extra swebench \
  -c swebench.yaml \
  -c "${MODEL_YAML}" \
  -c "${ENV_TESTBED_YAML}" \
  -c "model.litellm_model_registry=${REGISTRY_ABS}" \
  -c "environment.pull_timeout=7200" \
  -c "agent.step_limit=${STEP_LIMIT}" \
  --subset "${SUBSET}" \
  --split "${SPLIT}" \
  "${FILTER_ARGS[@]}" \
  -w "${WORKERS}" \
  -o "${OUT_DIR}"

PREDS="${OUT_DIR}/preds.json"
[[ -f "${PREDS}" ]] || { echo "[eval ERROR] missing ${PREDS}" >&2; exit 1; }

echo "[eval] harness → ${EVAL_DIR}  (python=${HARNESS_PYTHON})"
if ! "${HARNESS_PYTHON}" -c "import docker, swebench" >/dev/null 2>&1; then
  echo "[eval ERROR] HARNESS_PYTHON missing packages: need 'docker' and 'swebench'" >&2
  echo "  tried: ${HARNESS_PYTHON}" >&2
  echo "  Note: Docker CLI can exist while the Python 'docker' SDK is missing." >&2
  echo "  Fix:  pip install docker swebench   OR set HARNESS_PYTHON=/workspace/.conda/bin/python" >&2
  exit 1
fi
# Some swebench builds ignore --report_dir and write <model>.<run_id>.json to CWD.
# Always collect the report into EVAL_DIR afterward so metrics can find it.
"${HARNESS_PYTHON}" "${SCRIPT_DIR}/run_harness.py" \
  --dataset_name "${DATASET_NAME}" \
  --predictions_path "${PREDS}" \
  --max_workers "${HARNESS_WORKERS}" \
  --run_id "${RUN_ID}" \
  --report_dir "${EVAL_DIR}" \
  --cache_level instance \
  --clean False

mkdir -p "${EVAL_DIR}"
REPORT_GLOB="*.${RUN_ID}.json"
# Prefer CWD (common when report_dir is ignored), then report_dir itself.
for cand in \
  "./${REPORT_GLOB}" \
  "${EVAL_DIR}/${REPORT_GLOB}" \
  "${OUT_DIR}/${REPORT_GLOB}"
do
  # shellcheck disable=SC2086
  for f in ${cand}; do
    [[ -f "${f}" ]] || continue
    base="$(basename "${f}")"
    if [[ "${f}" != "${EVAL_DIR}/${base}" ]]; then
      cp -f "${f}" "${EVAL_DIR}/${base}"
      echo "[eval] collected harness report → ${EVAL_DIR}/${base}"
    else
      echo "[eval] harness report → ${f}"
    fi
  done
done

echo "[eval] done"
echo "[eval] preds : ${PREDS}"
echo "[eval] report: ${EVAL_DIR}"
echo "[eval] stats : GET ${ADAPTER_BASE}/stats"
