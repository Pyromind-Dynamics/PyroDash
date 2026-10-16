#!/usr/bin/env bash
# Math eval client against a running offload_math adapter.
#
# 1) Start adapter (separate terminal):
#      MODEL_PATH=... LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \
#        bash offload/offload_math/api.sh
# 2) Then:
#      bash evaluation/evaluation_math/math_eval.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"

ADAPTER_HOST="${ADAPTER_HOST:-127.0.0.1}"
ADAPTER_PORT="${ADAPTER_PORT:-18031}"
OUTPUT_DIR="${OUTPUT_DIR:-${SCRIPT_DIR}/output/results}"
DATASETS="${DATASETS:-gsm8k minerva olympiad aime2024 aime2025}"
MAX_TOKENS="${MAX_TOKENS:-8192}"
MAX_WORKERS="${MAX_WORKERS:-256}"
PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || command -v python)}"

HEALTH_URL="http://${ADAPTER_HOST}:${ADAPTER_PORT}/health"
echo "[eval] checking ${HEALTH_URL}"
if ! curl -sf --max-time 5 "${HEALTH_URL}" >/dev/null; then
  echo "[eval ERROR] adapter not ready at ${HEALTH_URL}" >&2
  echo "  Start first, e.g.:" >&2
  echo "    MODEL_PATH=... LLM_BASE_URL=... LLM_API_KEY=... LLM_MODEL=... \\" >&2
  echo "      bash ${REPO_ROOT}/offload/offload_math/api.sh" >&2
  exit 1
fi
echo "[eval] adapter ready"

mkdir -p "${OUTPUT_DIR}"
# shellcheck disable=SC2086
"${PYTHON_BIN}" "${SCRIPT_DIR}/math_eval.py" \
  --adapter-host "${ADAPTER_HOST}" \
  --adapter-port "${ADAPTER_PORT}" \
  --output-dir "${OUTPUT_DIR}" \
  --datasets ${DATASETS} \
  --max-tokens "${MAX_TOKENS}" \
  --max-workers "${MAX_WORKERS}"

echo "[eval] done → ${OUTPUT_DIR}"
