#!/usr/bin/env bash
# Historical short-sweep qualification; steady.py runs the sustained profile.
set -euo pipefail
run_id="${1:-$(date -u +%Y%m%dT%H%M%SZ)}"
mix format
mix compile --warnings-as-errors
mix format --check-formatted
python3 scripts/completion_probe.py "${run_id}-audit"
python3 scripts/count_audit.py "${run_id}-audit"
python3 scripts/matrix.py "${run_id}-matrix"
python3 scripts/matrix.py "${run_id}-pool-sweep" pool
python3 scripts/matrix.py "${run_id}-controls" controls
python3 scripts/summarise.py "${run_id}-matrix" "${run_id}-pool-sweep" "${run_id}-controls"
