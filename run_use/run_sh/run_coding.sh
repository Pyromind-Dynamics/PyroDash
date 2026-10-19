#!/usr/bin/env bash
# Unified coding eval pipeline: start offload adapter → run one benchmark → run_use/output/<RUN_ID>.
#
# MODE:
#   swe            SWE-bench Verified full (no instance filter)
#   swe_20filter   SWE-bench representative 20 (special case)
#   deepswe        DeepSWE 1.1 via Pier
#   terminal       Terminal-Bench via Harbor
#
#   MODE=swe bash run_use/run_sh/run_coding.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUN_USE_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
PYRODASH_ROOT="$(cd "${RUN_USE_ROOT}/.." && pwd)"

# shellcheck disable=SC1091
source "${PYRODASH_ROOT}/env_paths.sh"
# vLLM / adapter / pipeline → project .venv
pyrodash_activate_venv "${VENV_DIR:-${PYRODASH_VENV_DIR}}"

# =========================
# Edit this block (or export env vars before running)
# =========================

MODE="${MODE:-swe_20filter}"
CLUSTER="${CLUSTER:-us}"

# --- Small model (pick ONE) ---
MODEL_PATH="${MODEL_PATH:-}"
SLM_BASE_URL="${SLM_BASE_URL:-}"
SLM_API_KEY="${SLM_API_KEY:-dummy}"
SLM_MODEL="${SLM_MODEL:-}"

export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0}"

LLM_BASE_URL="${LLM_BASE_URL:-https://your-llm-host/v1}"
LLM_API_KEY="${LLM_API_KEY:-your-llm-api-key}"
LLM_MODEL="${LLM_MODEL:-your-llm-model}"

# tag | entropy | slm_only (slm_only → tag adapter + USE_LLM=false)
ROUTER_MODE="${ROUTER_MODE:-tag}"
OFFLOAD_MODE="${OFFLOAD_MODE:-handoff}"
USE_LLM="${USE_LLM:-true}"

SLM_BACKEND="${SLM_BACKEND:-vllm}"
SLM_PORT="${SLM_PORT:-${VLLM_PORT:-8007}}"
VLLM_PORT="${SLM_PORT}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-}"
ADAPTER_HOST="${ADAPTER_HOST:-0.0.0.0}"
ADAPTER_PORT="${ADAPTER_PORT:-18027}"

# SWE / shared workers
WORKERS="${WORKERS:-4}"
HARNESS_WORKERS="${HARNESS_WORKERS:-8}"
STEP_LIMIT="${STEP_LIMIT:-150}"

# DeepSWE / Terminal concurrency
N_CONCURRENT="${N_CONCURRENT:-${WORKERS}}"
N_TASKS="${N_TASKS:-}"
DEEPSWE_TASKS="${DEEPSWE_TASKS:-/workspace/work/mjy/eval/deep-swe/tasks}"
TB_DATASET="${TB_DATASET:-terminal-bench/terminal-bench-2-1}"

RUN_ID="${RUN_ID:-${MODE}_$(date '+%Y%m%d_%H%M%S')}"
# SWE harness verify → base conda (swebench + docker). Never gui-360 / .venv.
# Shanghai prefers eval_code only when HARNESS_PYTHON was not set and that env can import the harness packages.
if [[ "${CLUSTER}" == "shanghai" && -z "${HARNESS_PYTHON:-}" && -x /workspace/.conda/envs/eval_code/bin/python ]]; then
  if /workspace/.conda/envs/eval_code/bin/python -c "import docker, swebench" >/dev/null 2>&1; then
    export HARNESS_PYTHON=/workspace/.conda/envs/eval_code/bin/python
  fi
fi
pyrodash_resolve_harness_python || true
echo "[run] PYTHON_BIN=${PYTHON_BIN} VLLM_BIN=${VLLM_BIN:-} HARNESS_PYTHON=${HARNESS_PYTHON}"

# swe_20filter only — ignored for MODE=swe
SWE20_FILTER="astropy__astropy-14182|astropy__astropy-14508|django__django-10999|django__django-12262|django__django-13023|django__django-14122|django__django-15268|django__django-16136|django__django-16631|matplotlib__matplotlib-26208|pydata__xarray-3677|pydata__xarray-4094|pylint-dev__pylint-6528|pytest-dev__pytest-6202|scikit-learn__scikit-learn-14894|sphinx-doc__sphinx-10449|sphinx-doc__sphinx-9591|sympy__sympy-13551|sympy__sympy-14531|sympy__sympy-17139"
INSTANCE_FILTER="${INSTANCE_FILTER:-}"

# =========================

case "${MODE}" in
  swe|swe_20filter|deepswe|terminal) ;;
  *) echo "[run ERROR] MODE must be swe|swe_20filter|deepswe|terminal (got ${MODE})" >&2; exit 1 ;;
esac
case "${CLUSTER}" in
  us|shanghai) ;;
  *) echo "[run ERROR] CLUSTER must be us|shanghai (got ${CLUSTER})" >&2; exit 1 ;;
esac
export CLUSTER
case "${ROUTER_MODE}" in
  tag|entropy|slm_only) ;;
  *) echo "[run ERROR] ROUTER_MODE must be tag|entropy|slm_only (got ${ROUTER_MODE})" >&2; exit 1 ;;
esac

ADAPTER_KIND="${ROUTER_MODE}"
if [[ "${ROUTER_MODE}" == "slm_only" ]]; then
  ADAPTER_KIND="tag"
  USE_LLM=false
  echo "[run] ROUTER_MODE=slm_only → tag adapter, USE_LLM=false"
else
  USE_LLM=true
fi

API_SH="${PYRODASH_ROOT}/offload/offload_code/${ADAPTER_KIND}/api.sh"
[[ -f "${API_SH}" ]] || { echo "[run ERROR] missing ${API_SH}" >&2; exit 1; }

case "${MODE}" in
  swe|swe_20filter)
    EVAL_SH="${PYRODASH_ROOT}/evaluation/evaluation_code/swe-bench/eval.sh"
    ;;
  deepswe)
    EVAL_SH="${PYRODASH_ROOT}/evaluation/evaluation_code/deepswe1.1/eval.sh"
    ;;
  terminal)
    EVAL_SH="${PYRODASH_ROOT}/evaluation/evaluation_code/terminal-sh/eval.sh"
    ;;
esac
[[ -f "${EVAL_SH}" ]] || { echo "[run ERROR] missing ${EVAL_SH}" >&2; exit 1; }

if [[ "${MODE}" == "swe_20filter" && -z "${INSTANCE_FILTER}" ]]; then
  INSTANCE_FILTER="${SWE20_FILTER}"
fi
if [[ "${MODE}" == "swe" ]]; then
  INSTANCE_FILTER=""
fi

RUN_DIR="${RUN_USE_ROOT}/output/${RUN_ID}"
LOG_DIR="${RUN_DIR}/logs"
EVAL_OUT="${RUN_DIR}/${MODE}"
# Never wipe EVAL_OUT / preds.json — same RUN_ID reuses artifacts (SWE skips done).
mkdir -p "${LOG_DIR}" "${EVAL_OUT}"

STATUS_FILE="${RUN_DIR}/status.json"
ADAPTER_PID=""
PIPELINE_EXIT=1
RESUME="${RESUME:-0}"

write_status() {
  local phase="$1"
  local message="${2:-}"
  local extra="${3:-}"
  "${PYTHON_BIN}" - "${STATUS_FILE}" "${phase}" "${message}" "${RUN_ID}" "${ROUTER_MODE}" "${MODE}" "${OFFLOAD_MODE}" "${CLUSTER}" "${extra}" <<'PY'
import json, sys, time
from pathlib import Path
path, phase, message, run_id, router, mode, offload_mode, cluster, extra = sys.argv[1:10]
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
    "mode": mode,
    "cluster": cluster,
    "router_mode": router,
    "offload_mode": offload_mode,
    "phase": phase,
    "message": message,
    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
}
if phase == "starting_adapter" and "started_at" not in data:
    data["started_at"] = data["updated_at"]
if phase in ("starting_adapter", "evaluating"):
    data.pop("finished_at", None)
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
    write_status "done" "${MODE} finished"
  else
    local cur_phase=""
    cur_phase="$("${PYTHON_BIN}" -c "import json; print(json.load(open('${STATUS_FILE}')).get('phase',''))" 2>/dev/null || true)"
    if [[ "${cur_phase}" != "done" && "${cur_phase}" != "failed" ]]; then
      write_status "failed" "pipeline exited with code ${code}"
    fi
  fi
}
trap on_exit EXIT INT TERM

if [[ "${RESUME}" == "1" || "${RESUME}" == "true" || "${RESUME}" == "yes" ]]; then
  write_status "starting_adapter" "resuming ${ROUTER_MODE} offload adapter"
else
  write_status "starting_adapter" "launching ${ROUTER_MODE} offload adapter"
fi

export MODEL_PATH SLM_BASE_URL SLM_API_KEY SLM_MODEL
export LLM_BASE_URL LLM_API_KEY LLM_MODEL
export CUDA_VISIBLE_DEVICES
export SLM_BACKEND SLM_PORT VLLM_PORT MAX_MODEL_LEN
export ADAPTER_HOST ADAPTER_PORT OFFLOAD_MODE USE_LLM PYTHON_BIN
export WORKERS HARNESS_WORKERS STEP_LIMIT
export VLLM_BIN VLLM_CONDA_PREFIX VIRTUAL_ENV PATH
export OFFLOAD_LOG_DIR="${LOG_DIR}"
export TOKEN_USAGE_DIR="${LOG_DIR}/adapter_stats"
# Optional engine extras / binaries (only export when set — set -u safe)
[[ -v VLLM_EXTRA_ARGS ]] && export VLLM_EXTRA_ARGS
[[ -v SGLANG_EXTRA_ARGS ]] && export SGLANG_EXTRA_ARGS
[[ -v SGLANG_BIN ]] && export SGLANG_BIN
[[ -v SGLANG_PYTHON ]] && export SGLANG_PYTHON

ADAPTER_LOG="${LOG_DIR}/adapter_api.log"
if [[ "${CLUSTER}" == "shanghai" ]]; then
  export DOCKER_HOST="${DOCKER_HOST:-unix:///tmp/docker-rt.sock}"
  echo "[run] CLUSTER=shanghai DOCKER_HOST=${DOCKER_HOST}"
else
  echo "[run] CLUSTER=us"
fi

echo "[run] MODE=${MODE} RUN_ID=${RUN_ID} RESUME=${RESUME} SLM_BACKEND=${SLM_BACKEND}"
echo "[run] RUN_DIR=${RUN_DIR}"
if [[ "${RESUME}" == "1" || "${RESUME}" == "true" || "${RESUME}" == "yes" ]]; then
  echo "[run] resume: keeping existing ${EVAL_OUT} (SWE skips preds.json keys)"
fi
echo "[run] starting ${API_SH} → ${ADAPTER_LOG}"

setsid bash "${API_SH}" >"${ADAPTER_LOG}" 2>&1 &
ADAPTER_PID=$!

HEALTH_URL="http://127.0.0.1:${ADAPTER_PORT}/health"
DEADLINE=$((SECONDS + 1800))
echo "[run] waiting for ${HEALTH_URL}" | tee -a "${ADAPTER_LOG}"
while (( SECONDS < DEADLINE )); do
  if ! kill -0 "${ADAPTER_PID}" 2>/dev/null; then
    echo "[run ERROR] adapter exited early; see ${ADAPTER_LOG}" >&2
    write_status "failed" "adapter exited early"
    exit 1
  fi
  if curl -sf --max-time 2 "${HEALTH_URL}" >/dev/null 2>&1; then
    echo "[run] adapter ready" | tee -a "${ADAPTER_LOG}"
    break
  fi
  echo "[run] still waiting for adapter health… ($(date '+%H:%M:%S'))" >>"${ADAPTER_LOG}"
  sleep 2
done
if ! curl -sf --max-time 2 "${HEALTH_URL}" >/dev/null 2>&1; then
  echo "[run ERROR] adapter not ready; see ${ADAPTER_LOG}" >&2
  write_status "failed" "adapter health timeout"
  exit 1
fi

HOST_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
HOST_IP="${HOST_IP:-127.0.0.1}"

write_status "evaluating" "running ${MODE}" \
  "{\"adapter_port\": ${ADAPTER_PORT}, \"host_ip\": \"${HOST_IP}\"}"

EVAL_LOG="${LOG_DIR}/eval.log"
echo "[run] eval → ${EVAL_OUT} (log ${EVAL_LOG})"
# Unbuffered python so trajectory / progress lines show up sooner in eval.log
export PYTHONUNBUFFERED=1
export PYTHONPATH="${PYTHONPATH:-}"

# Background: refresh status.json progress from preds while eval runs
(
  while kill -0 "${ADAPTER_PID}" 2>/dev/null; do
    sleep 15
    [[ -f "${STATUS_FILE}" ]] || continue
    "${PYTHON_BIN}" - "${STATUS_FILE}" "${EVAL_OUT}" "${MODE}" <<'PY' || true
import json, sys, time
from pathlib import Path
status_path, eval_out, mode = sys.argv[1:4]
p = Path(status_path)
try:
    data = json.loads(p.read_text())
except Exception:
    raise SystemExit(0)
runs = Path(eval_out) / "runs"
done = []
preds = runs / "preds.json"
if preds.is_file():
    try:
        d = json.loads(preds.read_text())
        if isinstance(d, dict):
            done = sorted(d.keys())
    except Exception:
        pass
if not done and runs.is_dir():
    done = sorted(x.name for x in runs.iterdir() if x.is_dir())
total = 20 if mode == "swe_20filter" else None
data["progress"] = {
    "done": len(done),
    "total": total,
    "completed": done,
    "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
}
data["message"] = (
    f"{len(done)}/{total} instances done" if total else f"{len(done)} instances done"
)
data["updated_at"] = data["progress"]["updated_at"]
p.write_text(json.dumps(data, indent=2) + "\n")
PY
  done
) &
PROGRESS_PID=$!

set +e
case "${MODE}" in
  swe|swe_20filter)
    if [[ "${CLUSTER}" == "shanghai" ]]; then
      export MSWEA_NO_DOCKER_WRAPPER=1
      unset MSWEA_DOCKER_EXECUTABLE
      export SWEBENCH_DOCKER_IMAGE_PREFIX="${SWEBENCH_DOCKER_IMAGE_PREFIX:-pyromind-registry-vpc.cn-shanghai.cr.aliyuncs.com/pyromind}"
      export SWEBENCH_DOCKER_NAMESPACE="${SWEBENCH_DOCKER_NAMESPACE:-${SWEBENCH_DOCKER_IMAGE_PREFIX}}"
      export HF_HUB_OFFLINE="${HF_HUB_OFFLINE:-1}"
      export HF_DATASETS_OFFLINE="${HF_DATASETS_OFFLINE:-1}"
      export TRANSFORMERS_OFFLINE="${TRANSFORMERS_OFFLINE:-1}"
      export LITELLM_LOCAL_MODEL_COST_MAP="${LITELLM_LOCAL_MODEL_COST_MAP:-True}"
      export SWEBENCH_GITHUB_CACHE="${SWEBENCH_GITHUB_CACHE:-${PYRODASH_ROOT}/evaluation/evaluation_code/swe-bench/cache/github_raw}"
      export SWEBENCH_GITHUB_RAW_MIRRORS="${SWEBENCH_GITHUB_RAW_MIRRORS:-https://ghproxy.net/}"
      export SWEBENCH_GITHUB_RAW_TIMEOUT="${SWEBENCH_GITHUB_RAW_TIMEOUT:-30}"
      mkdir -p "${SWEBENCH_GITHUB_CACHE}"
      echo "[run] shanghai SWE prefix=${SWEBENCH_DOCKER_IMAGE_PREFIX} harness=${HARNESS_PYTHON}"
    fi
    EVAL_OUTPUT_DIR="${EVAL_OUT}" \
    INSTANCE_FILTER="${INSTANCE_FILTER}" \
    WORKERS="${WORKERS}" \
    HARNESS_WORKERS="${HARNESS_WORKERS}" \
    STEP_LIMIT="${STEP_LIMIT}" \
    RUN_ID="${RUN_ID}_pred" \
    PYTHON_BIN="${PYTHON_BIN}" \
    HARNESS_PYTHON="${HARNESS_PYTHON}" \
      bash "${EVAL_SH}" --host "${HOST_IP}" --port "${ADAPTER_PORT}" \
      >"${EVAL_LOG}" 2>&1
    EVAL_RC=$?
    ;;
  deepswe)
    EVAL_OUTPUT_DIR="${EVAL_OUT}" \
    DEEPSWE_TASKS="${DEEPSWE_TASKS}" \
    TASKS_DIR="${DEEPSWE_TASKS}" \
    N_CONCURRENT="${N_CONCURRENT}" \
    N_TASKS="${N_TASKS}" \
    JOB_NAME="${RUN_ID}" \
      bash "${EVAL_SH}" --host "${HOST_IP}" --port "${ADAPTER_PORT}" \
      ${N_TASKS:+--n-tasks "${N_TASKS}"} \
      --n "${N_CONCURRENT}" \
      --job-name "${RUN_ID}" \
      >"${EVAL_LOG}" 2>&1
    EVAL_RC=$?
    ;;
  terminal)
    EVAL_OUTPUT_DIR="${EVAL_OUT}" \
    DATASET="${TB_DATASET}" \
    N_CONCURRENT="${N_CONCURRENT}" \
    N_TASKS="${N_TASKS}" \
    JOB_NAME="${RUN_ID}" \
      bash "${EVAL_SH}" --host "${HOST_IP}" --port "${ADAPTER_PORT}" \
      ${N_TASKS:+--n-tasks "${N_TASKS}"} \
      --n "${N_CONCURRENT}" \
      --job-name "${RUN_ID}" \
      >"${EVAL_LOG}" 2>&1
    EVAL_RC=$?
    ;;
esac
set -e

kill "${PROGRESS_PID}" 2>/dev/null || true
wait "${PROGRESS_PID}" 2>/dev/null || true

tail -n 40 "${EVAL_LOG}" || true

# Upsert this run into run_use/result.md (same columns / prices as history tables)
# Use a heredoc (not python -c with nested quotes) — nested f\"...\" breaks bash parsing.
if [[ -f "${RUN_USE_ROOT}/html/metrics.py" ]]; then
  (
    cd "${RUN_USE_ROOT}/html"
    "${PYTHON_BIN}" - "${RUN_DIR}" "${RUN_USE_ROOT}/result.md" <<'PY'
from pathlib import Path
import sys
from metrics import persist_run_to_result_md

run_dir, result_md = Path(sys.argv[1]), Path(sys.argv[2])
out = persist_run_to_result_md(run_dir, result_md)
row = out.get("row") or {}
print(
    f"[run] result.md written={out.get('written')} "
    f"mode={out.get('mode')} score={row.get('score')}"
)
PY
  ) || true
fi

if [[ "${EVAL_RC}" -ne 0 ]]; then
  write_status "failed" "eval.sh exited ${EVAL_RC}"
  exit "${EVAL_RC}"
fi

PIPELINE_EXIT=0
write_status "done" "${MODE} finished"
echo "[run] done → ${RUN_DIR}"
echo "[run] status → ${STATUS_FILE}"
