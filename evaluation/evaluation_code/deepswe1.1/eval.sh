#!/usr/bin/env bash
# DeepSWE 1.1 via Pier against a running offload_code adapter.
# Start the adapter first (offload/offload_code/{tag|entropy}/api.sh), then:
#
#   bash eval.sh --port 18027
#   bash eval.sh --host 10.0.0.1 --port 18027 --smoke
#
# Agent runs inside Docker — do NOT use 127.0.0.1 as --host unless you know
# the container can reach it. Default host is auto-detected via hostname -I.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUT_DIR="${SCRIPT_DIR}/output"
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
N_CONCURRENT="${N_CONCURRENT:-4}"
N_TASKS="${N_TASKS:-}"
SAMPLE_SEED="${SAMPLE_SEED:-0}"
JOB_NAME="${JOB_NAME:-deepswe1.1-$(date +%Y%m%d-%H%M%S)}"
TASKS_DIR="${TASKS_DIR:-${DEEPSWE_TASKS:-}}"
MODEL_NAME="${MODEL_NAME:-openai/pyrodash_code}"
EXTRA_PIER_ARGS=()

usage() {
  cat <<EOF
Usage: bash eval.sh --port PORT [--host HOST] [--smoke]

Requires a running offload adapter (GET /health).

Options:
  --host HOST          Adapter host reachable from Docker agents
                       (default: auto-detect hostname -I / HOST_IP)
  --port PORT          Adapter port (required; or set ADAPTER_PORT)
  --smoke              N_TASKS=1 N_CONCURRENT=1
  --job-name NAME      Pier job name under output/
  --n N                Concurrent trials (default: ${N_CONCURRENT})
  --n-tasks N          Limit tasks via pier -l (empty = all)
  -h, --help           Show this help

Env:
  TASKS_DIR / DEEPSWE_TASKS   Path to deep-swe tasks/ (required)
  SAMPLE_SEED                 Default 0 (with -l)
  MODEL_NAME                  Default openai/pyrodash_code
  DOCKER_HOST                 Optional Docker socket override
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
    -h|--help)
      usage
      exit 0
      ;;
    --)
      shift
      EXTRA_PIER_ARGS+=("$@")
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

if [[ -z "${TASKS_DIR}" ]]; then
  echo "[eval ERROR] set TASKS_DIR or DEEPSWE_TASKS to deep-swe tasks/ directory" >&2
  echo "  e.g. DEEPSWE_TASKS=/path/to/deep-swe/tasks" >&2
  echo "  or:  git clone https://github.com/datacurve-ai/deep-swe && export DEEPSWE_TASKS=\$PWD/deep-swe/tasks" >&2
  exit 1
fi
[[ -d "${TASKS_DIR}" ]] || { echo "[eval ERROR] TASKS_DIR not a directory: ${TASKS_DIR}" >&2; exit 1; }

if ! command -v pier >/dev/null 2>&1; then
  echo "[eval ERROR] pier not found; install: uv tool install datacurve-pier" >&2
  exit 1
fi

ADAPTER_BASE="http://${ADAPTER_HOST}:${ADAPTER_PORT}"
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

export OPENAI_BASE_URL="${API_BASE}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-dummy}"
unset MSWEA_API_KEY || true

cmd=(
  pier run
  -p "${TASKS_DIR}"
  -a mini-swe-agent
  -m "${MODEL_NAME}"
  -n "${N_CONCURRENT}"
  -o "${OUT_DIR}"
  --job-name "${JOB_NAME}"
  --ak 'cost_limit=9999'
  --ak 'model_class=litellm'
  --ak 'model_kwargs={"drop_params":true,"timeout":3000}'
  -y
)

if [[ -n "${N_TASKS}" ]]; then
  cmd+=(-l "${N_TASKS}" --sample-seed "${SAMPLE_SEED}")
fi
if [[ ${#EXTRA_PIER_ARGS[@]} -gt 0 ]]; then
  cmd+=("${EXTRA_PIER_ARGS[@]}")
fi

echo "[eval] Pier -> ${API_BASE}  model=${MODEL_NAME}"
echo "[eval] tasks=${TASKS_DIR}  concurrent=${N_CONCURRENT}  n_tasks=${N_TASKS:-all}"
echo "[eval] Running: ${cmd[*]}"
echo "[eval] Results -> ${OUT_DIR}/${JOB_NAME}/"
"${cmd[@]}"

echo "[eval] done"
echo "[eval] job    : ${OUT_DIR}/${JOB_NAME}/"
echo "[eval] result : ${OUT_DIR}/${JOB_NAME}/result.json"
echo "[eval] rewards: ${OUT_DIR}/${JOB_NAME}/*/verifier/reward.json"
echo "[eval] stats  : GET ${ADAPTER_BASE}/stats"
