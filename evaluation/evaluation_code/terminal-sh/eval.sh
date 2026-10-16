#!/usr/bin/env bash
# Terminal-Bench via Harbor against a running offload_code adapter.
# Start the adapter first (offload/offload_code/{tag|entropy}/api.sh), then:
#
#   bash eval.sh --port 18027
#   bash eval.sh --host 10.0.0.1 --port 18027 --smoke
#
# Agent runs inside Docker — default host is auto-detected (not 127.0.0.1).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# If EVAL_OUTPUT_DIR is set, redirect Harbor job output there (for run_use pipelines).
OUT_DIR="${EVAL_OUTPUT_DIR:-${SCRIPT_DIR}/output}"
mkdir -p "${OUT_DIR}"

detect_host_ip() {
  local ip=""
  ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  if [[ -z "${ip}" ]]; then
    ip="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
  fi
  echo "${ip:-127.0.0.1}"
}

ADAPTER_HOST="${ADAPTER_HOST:-${HOST_IP:-}}"
ADAPTER_PORT="${ADAPTER_PORT:-}"
HOST_EXPLICIT=0
DATASET="${DATASET:-terminal-bench/terminal-bench-2-1}"
N_CONCURRENT="${N_CONCURRENT:-4}"
N_TASKS="${N_TASKS:-}"
INCLUDE_TASK="${INCLUDE_TASK:-}"
JOB_NAME="${JOB_NAME:-tb-$(date +%Y%m%d-%H%M%S)}"
MODEL_NAME="${MODEL_NAME:-openai/pyrodash_code}"
EXTRA_HARBOR_ARGS=()

usage() {
  cat <<EOF
Usage: bash eval.sh --port PORT [--host HOST] [--smoke]

Requires a running offload adapter (GET /health or /v1/models).

Options:
  --host HOST          Adapter host reachable from Docker agents
                       (default: auto-detect hostname -I / HOST_IP)
  --port PORT          Adapter port (required; or set ADAPTER_PORT)
  --smoke              N_TASKS=1 N_CONCURRENT=1
  --job-name NAME      Harbor job name under output/
  --n N                Concurrent trials (default: ${N_CONCURRENT})
  --n-tasks N          Harbor -l limit (empty = all)
  --include-task NAME  Harbor -i task name
  -h, --help           Show this help

Env:
  EVAL_OUTPUT_DIR      if set, write Harbor jobs under this directory
  DATASET              Default terminal-bench/terminal-bench-2-1
                       (e.g. terminal-bench@2.0)
  MODEL_NAME           Default openai/pyrodash_code
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)
      ADAPTER_HOST="$2"
      HOST_EXPLICIT=1
      shift 2
      ;;
    --port)
      ADAPTER_PORT="$2"
      shift 2
      ;;
    --smoke)
      N_TASKS=1
      N_CONCURRENT=1
      shift
      ;;
    --job-name)
      JOB_NAME="$2"
      shift 2
      ;;
    --n)
      N_CONCURRENT="$2"
      shift 2
      ;;
    --n-tasks)
      N_TASKS="$2"
      shift 2
      ;;
    --include-task)
      INCLUDE_TASK="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      EXTRA_HARBOR_ARGS+=("$@")
      break
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

if [[ -z "${ADAPTER_HOST}" ]]; then
  ADAPTER_HOST="$(detect_host_ip)"
fi
if [[ "${HOST_EXPLICIT}" -eq 0 && "${ADAPTER_HOST}" == "127.0.0.1" ]]; then
  echo "[eval WARN] host is 127.0.0.1 — Docker agents often cannot reach it; set --host <宿主机IP>" >&2
fi

if ! command -v harbor >/dev/null 2>&1; then
  echo "[eval ERROR] harbor not found on PATH" >&2
  exit 1
fi

ADAPTER_BASE="http://${ADAPTER_HOST}:${ADAPTER_PORT}"
API_BASE="${ADAPTER_BASE}/v1"

echo "[eval] checking adapter at ${ADAPTER_BASE}"
if ! curl -sf --max-time 5 "${ADAPTER_BASE}/health" >/dev/null \
  && ! curl -sf --max-time 5 "${API_BASE}/models" >/dev/null; then
  echo "[eval ERROR] adapter not ready at ${ADAPTER_BASE}" >&2
  echo "  Start offload first, e.g.:" >&2
  echo "    ADAPTER_PORT=${ADAPTER_PORT} bash offload/offload_code/tag/api.sh" >&2
  exit 1
fi
echo "[eval] adapter ready (OpenAI api_base=${API_BASE})"

export OPENAI_BASE_URL="${API_BASE}"
export OPENAI_API_BASE="${API_BASE}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-dummy}"
unset MSWEA_API_KEY || true

cmd=(
  harbor run
  -d "${DATASET}"
  -a mini-swe-agent
  -m "${MODEL_NAME}"
  -n "${N_CONCURRENT}"
  -o "${OUT_DIR}"
  --job-name "${JOB_NAME}"
  -y
)

if [[ -n "${N_TASKS}" ]]; then
  cmd+=(-l "${N_TASKS}")
fi
if [[ -n "${INCLUDE_TASK}" ]]; then
  cmd+=(-i "${INCLUDE_TASK}")
fi
if [[ ${#EXTRA_HARBOR_ARGS[@]} -gt 0 ]]; then
  cmd+=("${EXTRA_HARBOR_ARGS[@]}")
fi

echo "[eval] Harbor -> ${API_BASE}  model=${MODEL_NAME}"
echo "[eval] dataset=${DATASET}  concurrent=${N_CONCURRENT}  n_tasks=${N_TASKS:-all}"
echo "[eval] Running: ${cmd[*]}"
echo "[eval] Results -> ${OUT_DIR}/${JOB_NAME}/"
"${cmd[@]}"

echo "[eval] done"
echo "[eval] job    : ${OUT_DIR}/${JOB_NAME}/"
echo "[eval] result : ${OUT_DIR}/${JOB_NAME}/result.json"
echo "[eval] stats  : GET ${ADAPTER_BASE}/stats"
