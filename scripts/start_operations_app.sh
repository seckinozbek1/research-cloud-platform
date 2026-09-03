#!/usr/bin/env bash

# Operations Meta-Agent local launcher.
#
# Deliberately does NOT use:
#   set -e
#   EXIT traps
#   interactive-shell mutation
#
# It is safe to invoke from another shell without changing that shell's
# errexit behaviour.

set -u
set -o pipefail

SCRIPT_DIR="$(
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")" 2>/dev/null &&
    pwd
)"

if [[ -z "${SCRIPT_DIR:-}" ]]; then
    echo "ERROR: Could not determine launcher directory."
    return 1 2>/dev/null || exit 1
fi

PROJECT_ROOT="$(
    cd -- "${SCRIPT_DIR}/.." 2>/dev/null &&
    pwd
)"

if [[ -z "${PROJECT_ROOT:-}" ]]; then
    echo "ERROR: Could not determine project root."
    return 1 2>/dev/null || exit 1
fi

cd "$PROJECT_ROOT" || {
    echo "ERROR: Could not enter project root."
    return 1 2>/dev/null || exit 1
}

# Runtime activation is intentionally sourced.
# enter_runtime.sh must not enable errexit in the caller.
source "${SCRIPT_DIR}/enter_runtime.sh"

RUNTIME_STATUS=$?

if [[ $RUNTIME_STATUS -ne 0 ]]; then
    echo "ERROR: Could not activate the Research Cloud runtime."
    return "$RUNTIME_STATUS" 2>/dev/null || exit "$RUNTIME_STATUS"
fi


APP_HOST="${OPERATIONS_APP_HOST:-127.0.0.1}"
APP_PORT="${OPERATIONS_APP_PORT:-8000}"

MODEL_HOST="${QWEN_HOST:-127.0.0.1}"
MODEL_PORT="${QWEN_PORT:-8080}"

APP_URL="http://${APP_HOST}:${APP_PORT}"
APP_HEALTH="${APP_URL}/health"

MODEL_URL="http://${MODEL_HOST}:${MODEL_PORT}"
MODEL_HEALTH="${MODEL_URL}/health"

APP_LOG="${RESEARCH_CLOUD_RUNTIME}/operations-app.log"
MODEL_LOG="${RESEARCH_CLOUD_RUNTIME}/qwen-server.log"


http_ok() {
    local url="$1"

    python - "$url" <<'PY'
import sys
import urllib.request

url = sys.argv[1]

try:
    with urllib.request.urlopen(
        url,
        timeout=1.5,
    ) as response:
        if 200 <= response.status < 300:
            raise SystemExit(0)
except Exception:
    pass

raise SystemExit(1)
PY
}


wait_for_health() {
    local url="$1"
    local attempts="$2"
    local delay="$3"

    local attempt=1

    while [[ $attempt -le $attempts ]]; do
        if http_ok "$url"; then
            return 0
        fi

        sleep "$delay"
        attempt=$((attempt + 1))
    done

    return 1
}


open_browser() {
    local url="$1"

    if [[ "${OPERATIONS_NO_BROWSER:-0}" == "1" ]]; then
        return 0
    fi

    # WSL -> default Windows browser.
    if grep -qi microsoft /proc/version 2>/dev/null; then
        if command -v cmd.exe >/dev/null 2>&1; then
            cmd.exe /C start "" "$url" >/dev/null 2>&1
            return 0
        fi
    fi

    # Standard Linux desktop.
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$url" >/dev/null 2>&1
        return 0
    fi

    # macOS fallback.
    if command -v open >/dev/null 2>&1; then
        open "$url" >/dev/null 2>&1
        return 0
    fi

    return 1
}


echo "Starting Operations Meta-Agent..."


# If an existing healthy app owns the configured endpoint,
# use it instead of attempting to bind another server.
if http_ok "$APP_HEALTH"; then
    echo "Operations Meta-Agent is already running."

    open_browser "$APP_URL"

    BROWSER_STATUS=$?

    if [[ $BROWSER_STATUS -ne 0 ]]; then
        echo "Open this address in your browser:"
        echo "$APP_URL"
    fi

    return 0 2>/dev/null || exit 0
fi


# Start the local model only when it is not already healthy.
if ! http_ok "$MODEL_HEALTH"; then
    echo "Starting local language model..."

    bash "${SCRIPT_DIR}/start_qwen_server.sh" \
        >"$MODEL_LOG" \
        2>&1 &

    MODEL_PID=$!

    if ! wait_for_health "$MODEL_HEALTH" 90 1; then
        echo "ERROR: Local language model did not become ready."
        echo
        echo "Last model log lines:"
        tail -n 30 "$MODEL_LOG" 2>/dev/null

        return 1 2>/dev/null || exit 1
    fi
fi


echo "Starting local application server..."

python -m uvicorn \
    agent.web_app:app \
    --host "$APP_HOST" \
    --port "$APP_PORT" \
    >"$APP_LOG" \
    2>&1 &

APP_PID=$!


if ! wait_for_health "$APP_HEALTH" 30 1; then
    echo "ERROR: Operations Meta-Agent did not become ready."
    echo
    echo "Last application log lines:"
    tail -n 30 "$APP_LOG" 2>/dev/null

    if kill -0 "$APP_PID" 2>/dev/null; then
        kill "$APP_PID" 2>/dev/null
    fi

    return 1 2>/dev/null || exit 1
fi


echo "Operations Meta-Agent is ready."

open_browser "$APP_URL"

BROWSER_STATUS=$?

if [[ $BROWSER_STATUS -ne 0 ]]; then
    echo "Open this address in your browser:"
    echo "$APP_URL"
fi


# The launcher owns the foreground application server.
# No EXIT trap is used. This wait merely keeps the launcher process alive
# while the application is running.
wait "$APP_PID"
