#!/usr/bin/env bash
# SWE-bench Verified eval against a running offload adapter (see serve/serve_adapter.sh).
set -euo pipefail
export MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT=3

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
OUT="$SCRIPT_DIR/output/runs"
EVAL="$SCRIPT_DIR/output/verified"
mkdir -p "$OUT" "$EVAL"

curl -sf http://127.0.0.1:18022/health >/dev/null \
  || { echo "[eval ERROR] adapter not ready at http://127.0.0.1:18022 (run serve/serve_adapter.sh first)" >&2; exit 1; }

# ---------- 1) mini-extra swebench ----------
mini-extra swebench \
  -c swebench.yaml \
  -c "$SCRIPT_DIR/serve/config_yaml/model_offload.yaml" \
  -c "model.litellm_model_registry=$SCRIPT_DIR/serve/registry.json" \
  -c "environment.pull_timeout=7200" \
  -c "agent.step_limit=150" \
  --subset verified \
  --split test \
  -w 4 \
  -o "$OUT"

# ---------- 2) SWE-bench harness ----------
python "$SCRIPT_DIR/run_swebench_eval.py" \
  --dataset_name princeton-nlp/SWE-bench_Verified \
  --predictions_path "$OUT/preds.json" \
  --max_workers 8 \
  --run_id miniswe_offload_verified_pred \
  --report_dir "$EVAL" \
  --cache_level instance \
  --clean False

echo "[eval] done"
echo "[eval] preds: $OUT/preds.json"
echo "[eval] report: $EVAL"
