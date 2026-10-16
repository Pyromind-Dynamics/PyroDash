#!/usr/bin/env bash
# Thin wrapper → run_coding.sh MODE=swe_20filter
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
export MODE=swe_20filter
exec bash "${SCRIPT_DIR}/run_coding.sh" "$@"
