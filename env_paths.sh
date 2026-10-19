#!/usr/bin/env bash
# Moved to run_use/env_paths.sh — offload/evaluation must not source this.
# Kept as a thin redirect for older call sites.
# shellcheck disable=SC1091
source "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/run_use/env_paths.sh"
