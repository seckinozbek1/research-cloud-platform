#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${RESEARCH_CLOUD_PROJECT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PORT="5000"
RUN_ID="${1:?Usage: scripts/open_mlflow_context.sh <run_id>}"

cd "$PROJECT_ROOT"

EXPERIMENT_ID="$(
python3 - "$RUN_ID" <<'PY'
import sys
import mlflow

run_id = sys.argv[1]

mlflow.set_tracking_uri("sqlite:///mlflow.db")
run = mlflow.get_run(run_id)

print(run.info.experiment_id)
PY
)"

RUN_URL="http://127.0.0.1:${PORT}/#/experiments/${EXPERIMENT_ID}/runs/${RUN_ID}"
EXPERIMENT_URL="http://127.0.0.1:${PORT}/#/experiments/${EXPERIMENT_ID}/runs"

echo "Experiment ID : $EXPERIMENT_ID"
echo "Run ID        : $RUN_ID"

# First open the specific run.
cmd.exe /c start "" "$RUN_URL"

# Give the browser time to create/select the first tab.
sleep 2

# Then open the experiment's Training runs page in another browser tab.
cmd.exe /c start "" "$EXPERIMENT_URL"
