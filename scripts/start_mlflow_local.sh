#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="${RESEARCH_CLOUD_PROJECT_ROOT:-$(cd "$SCRIPT_DIR/.." && pwd)}"
WINDOW="mlflow"
PORT="5000"

SESSION="$(tmux display-message -p '#S')"

cd "$PROJECT_ROOT"

if tmux list-windows -t "$SESSION" -F '#W' 2>/dev/null | grep -qx "$WINDOW"; then
    echo "MLflow tmux window already exists."
else
    tmux new-window -t "$SESSION" -n "$WINDOW" \
        "cd '$PROJECT_ROOT' && source .venv/bin/activate && mlflow ui --backend-store-uri sqlite:///mlflow.db --host 127.0.0.1 --port $PORT 2>&1 | tee /tmp/mlflow_ui.log"
    echo "Started MLflow in tmux window: $WINDOW"
fi

sleep 2

explorer.exe "http://127.0.0.1:$PORT"
