#!/usr/bin/env bash
# Full pipeline: start offload adapter → SWE-bench representative 20filter → results under run_use/output/<RUN_ID>.
# Edit the config block (or export env vars), then:
#   bash run_use/run_sh/run_swe_20filter.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYRODASH_ROOT="$(cd "${RUN_USE_ROOT}/.." && pwd)"

# =========================
# Edit this block (or export env vars before running)
# =========================

# --- Small model (pick ONE) ---
# A) Local path → api.sh starts vLLM
MODEL_PATH="${MODEL_PATH:-}"
# B) Remote OpenAI-compatible SLM
SLM_BASE_URL="${SLM_BASE_URL:-}"
SLM_API_KEY="${SLM_API_KEY:-dummy}"
SLM_MODEL="${SLM_MODEL:-}"

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

# Remote LLM (OpenAI-compatible)
LLM_BASE_URL="${LLM_BASE_URL:-https://your-llm-host/v1}"
LLM_API_KEY="${LLM_API_KEY:-your-llm-api-key}"
LLM_MODEL="${LLM_MODEL:-your-llm-model}"

# Router: tag | entropy
ROUTER_MODE="${ROUTER_MODE:-tag}"
# offload mode for tag/entropy adapters: handoff | rewrite | keep
OFFLOAD_MODE="${OFFLOAD_MODE:-handoff}"

VLLM_PORT="${VLLM_PORT:-8007}"
ADAPTER_HOST="${ADAPTER_HOST:-0.0.0.0}"
ADAPTER_PORT="${ADAPTER_PORT:-18027}"

# Eval workers
WORKERS="${WORKERS:-4}"
HARNESS_WORKERS="${HARNESS_WORKERS:-8}"
STEP_LIMIT="${STEP_LIMIT:-150}"

RUN_ID="${RUN_ID:-swe20_$(date '+%Y%m%d_%H%M%S')}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || command -v python)}"

# Fixed representative 20filter (same as swe_run_offload/run_pipeline_20n.sh)
INSTANCE_FILTER="${INSTANCE_FILTER:-astropy__astropy-14182|astropy__astropy-14508|django__django-10999|django__django-12262|django__django-13023|django__django-14122|django__django-15268|django__django-16136|django__django-16631|matplotlib__matplotlib-26208|pydata__xarray-3677|pydata__xarray-4094|pylint-dev__pylint-6528|pytest-dev__pytest-6202|scikit-learn__scikit-learn-14894|sphinx-doc__sphinx-10449|sphinx-doc__sphinx-9591|sympy__sympy-13551|sympy__sympy-14531|sympy__sympy-17139}"

# =========================

case "${ROUTER_MODE}" in
  tag|entropy) ;;
  *) echo "[run ERROR] ROUTER_MODE must be tag or entropy (got ${ROUTER_MODE})" >&2; exit 1 ;;
esac

API_SH="${PYRODASH_ROOT}/offload/offload_code/${ROUTER_MODE}/api.sh"
EVAL_SH="${PYRODASH_ROOT}/evaluation/evaluation_code/swe-bench/eval.sh"
[[ -f "${API_SH}" ]] || { echo "[run ERROR] missing ${API_SH}" >&2; exit 1; }
[[ -f "${EVAL_SH}" ]] || { echo "[run ERROR] missing ${EVAL_SH}" >&2; exit 1; }

RUN_DIR="${RUN_USE_ROOT}/output/${RUN_ID}"
LOG_DIR="${RUN_DIR}/logs"
EVAL_OUT="${RUN_DIR}/swe_20filter"
mkdir -p "${LOG_DIR}" "${EVAL_OUT}"

STATUS_FILE="${RUN_DIR}/status.json"
ADAPTER_PID=""
PIPELINE_EXIT=1

write_status() {
  local phase="$1"
  local message="${2:-}"
  local extra="${3:-}"
  "${PYTHON_BIN}" - "${STATUS_FILE}" "${phase}" "${message}" "${RUN_ID}" "${ROUTER_MODE}" "${extra}" <<'PY'
import json, sys, time
from pathlib import Path
path, phase, message, run_id, router, extra = sys.argv[1:7]
prev = {}
p = Path(path)
if p.exists():
    try:
        prev = json.loads(p.read_text())
    except Exception:
        prev = {}
data = {
    **prev,
    "run_id": run_id,
    "mode": "swe_20filter",
    "router_mode": router,
    "phase": phase,
    "message": message,
    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
}
if phase == "starting_adapter" and "started_at" not in data:
    data["started_at"] = data["updated_at"]
if phase in ("done", "failed"):
    data["finished_at"] = data["updated_at"]
if extra:
    try:
        data.update(json.loads(extra))
    except Exception:
        pass
p.write_text(json.dumps(data, indent=2) + "\n")
PY
}

cleanup_adapter() {
  if [[ -n "${ADAPTER_PID}" ]] && kill -0 "${ADAPTER_PID}" 2>/dev/null; then
    echo "[run] stopping adapter pid=${ADAPTER_PID}"
    # Kill process group so vLLM children die with api.sh
    kill -TERM -"${ADAPTER_PID}" 2>/dev/null || kill -TERM "${ADAPTER_PID}" 2>/dev/null || true
    for _ in $(seq 1 30); do
      kill -0 "${ADAPTER_PID}" 2>/dev/null || break
      sleep 1
    done
    if kill -0 "${ADAPTER_PID}" 2>/dev/null; then
      kill -KILL -"${ADAPTER_PID}" 2>/dev/null || kill -KILL "${ADAPTER_PID}" 2>/dev/null || true
    fi
    wait "${ADAPTER_PID}" 2>/dev/null || true
  fi
  ADAPTER_PID=""
}

on_exit() {
  local code=$?
  cleanup_adapter
  if [[ "${PIPELINE_EXIT}" -eq 0 ]]; then
    write_status "done" "swe_20filter finished"
  else
    local cur_phase=""
    cur_phase="$("${PYTHON_BIN}" -c "import json; print(json.load(open('${STATUS_FILE}')).get('phase',''))" 2>/dev/null || true)"
    if [[ "${cur_phase}" != "done" && "${cur_phase}" != "failed" ]]; then
      write_status "failed" "pipeline exited with code ${code}"
    fi
  fi
}
trap on_exit EXIT INT TERM

write_status "starting_adapter" "launching ${ROUTER_MODE} offload adapter"

export MODEL_PATH SLM_BASE_URL SLM_API_KEY SLM_MODEL
export LLM_BASE_URL LLM_API_KEY LLM_MODEL
export CUDA_VISIBLE_DEVICES
export VLLM_PORT ADAPTER_HOST ADAPTER_PORT OFFLOAD_MODE PYTHON_BIN
# Point adapter token stats into this run's logs
export TOKEN_USAGE_DIR="${LOG_DIR}/adapter_stats"

ADAPTER_LOG="${LOG_DIR}/adapter_api.log"
echo "[run] RUN_ID=${RUN_ID}"
echo "[run] RUN_DIR=${RUN_DIR}"
echo "[run] starting ${API_SH} → ${ADAPTER_LOG}"

# New session so we can kill the whole tree on cleanup
setsid bash "${API_SH}" >"${ADAPTER_LOG}" 2>&1 &
ADAPTER_PID=$!

HEALTH_URL="http://127.0.0.1:${ADAPTER_PORT}/health"
DEADLINE=$((SECONDS + 600))
echo "[run] waiting for ${HEALTH_URL}"
while (( SECONDS < DEADLINE )); do
  if ! kill -0 "${ADAPTER_PID}" 2>/dev/null; then
    echo "[run ERROR] adapter exited early; see ${ADAPTER_LOG}" >&2
    write_status "failed" "adapter exited early"
    exit 1
  fi
  if curl -sf --max-time 2 "${HEALTH_URL}" >/dev/null 2>&1; then
    echo "[run] adapter ready"
    break
  fi
  sleep 2
done
if ! curl -sf --max-time 2 "${HEALTH_URL}" >/dev/null 2>&1; then
  echo "[run ERROR] adapter not ready; see ${ADAPTER_LOG}" >&2
  write_status "failed" "adapter health timeout"
  exit 1
fi

HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
HOST_IP="${HOST_IP:-127.0.0.1}"

write_status "evaluating" "mini-extra swebench 20filter + harness" \
  "{\"adapter_port\": ${ADAPTER_PORT}, \"host_ip\": \"${HOST_IP}\"}"

EVAL_LOG="${LOG_DIR}/eval.log"
echo "[run] eval → ${EVAL_OUT} (log ${EVAL_LOG})"

set +e
EVAL_OUTPUT_DIR="${EVAL_OUT}" \
INSTANCE_FILTER="${INSTANCE_FILTER}" \
WORKERS="${WORKERS}" \
HARNESS_WORKERS="${HARNESS_WORKERS}" \
STEP_LIMIT="${STEP_LIMIT}" \
RUN_ID="${RUN_ID}_pred" \
PYTHON_BIN="${PYTHON_BIN}" \
  bash "${EVAL_SH}" --host "${HOST_IP}" --port "${ADAPTER_PORT}" \
  >"${EVAL_LOG}" 2>&1
EVAL_RC=$?
set -e

# Also tee last lines to stdout for CLI visibility
tail -n 40 "${EVAL_LOG}" || true

if [[ "${EVAL_RC}" -ne 0 ]]; then
  write_status "failed" "eval.sh exited ${EVAL_RC}"
  exit "${EVAL_RC}"
fi

PIPELINE_EXIT=0
write_status "done" "swe_20filter finished"
echo "[run] done → ${RUN_DIR}"
echo "[run] status → ${STATUS_FILE}"
