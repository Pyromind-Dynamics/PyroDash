#!/usr/bin/env bash
# 只跑 harness 打分：用已有 preds.json，不起模型
set -euo pipefail

export CLUSTER=us
export HARNESS_PYTHON=/workspace/.conda/bin/python

PREDS=/workspace/work/mjy/PyroDash/run_use/output/swe_20filter_20261021_060238/swe_20filter/runs/preds.json
EVAL_DIR=/workspace/work/mjy/PyroDash/run_use/output/swe_20filter_20261021_060238/swe_20filter/verified
RUN_HARNESS=/workspace/work/mjy/PyroDash/evaluation/evaluation_code/swe-bench/run_harness.py

mkdir -p "${EVAL_DIR}"
cd "${EVAL_DIR}"

"${HARNESS_PYTHON}" "${RUN_HARNESS}" \
  --dataset_name SWE-bench/SWE-bench_Verified \
  --predictions_path "${PREDS}" \
  --max_workers 1 \
  --run_id swe_20filter_20261021_060238_pred \
  --report_dir "${EVAL_DIR}"

echo "[harness-only] done → ${EVAL_DIR}"
