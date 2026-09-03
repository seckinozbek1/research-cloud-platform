#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(
    cd "$(dirname "${BASH_SOURCE[0]}")"
    pwd
)"

PROJECT_ROOT="${RESEARCH_CLOUD_PROJECT_ROOT:-$(
    cd "$SCRIPT_DIR/.."
    pwd
)}"

if [[ -n "${RESEARCH_CLOUD_RUNTIME:-}" ]]; then
    RUNTIME="$RESEARCH_CLOUD_RUNTIME"
elif [[ -d "$HOME/research-cloud-runtime" ]]; then
    # Backward-compatible discovery for existing installations.
    RUNTIME="$HOME/research-cloud-runtime"
elif [[ "$(uname -s)" == "Darwin" ]]; then
    RUNTIME="$HOME/Library/Application Support/research-cloud-platform"
else
    RUNTIME="${XDG_DATA_HOME:-$HOME/.local/share}/research-cloud-platform"
fi

MODEL="${QWEN_MODEL:-Qwen/Qwen3-8B-GGUF:Q4_K_M}"
HOST="${QWEN_HOST:-127.0.0.1}"
PORT="${QWEN_PORT:-8080}"
CTX="${QWEN_CONTEXT_SIZE:-8192}"

MODEL_CACHE="${RESEARCH_CLOUD_MODEL_CACHE:-$RUNTIME/models/llama.cpp}"

if [[ -n "${LLAMA_BIN:-}" ]]; then
    LLAMA="$LLAMA_BIN"
elif command -v llama >/dev/null 2>&1; then
    LLAMA="$(command -v llama)"
elif [[ -x "$HOME/.llama-app/llama" ]]; then
    LLAMA="$HOME/.llama-app/llama"
else
    echo "llama.cpp launcher was not found."
    echo
    echo "Set LLAMA_BIN to the installed llama executable."
    exit 2
fi

mkdir -p \
    "$RUNTIME" \
    "$MODEL_CACHE"

if command -v curl >/dev/null 2>&1; then
    if curl \
        --silent \
        --fail \
        "http://$HOST:$PORT/health" \
        >/dev/null 2>&1
    then
        echo "Qwen server is already responding at:"
        echo "  http://$HOST:$PORT"
        exit 0
    fi
fi

export RESEARCH_CLOUD_PROJECT_ROOT="$PROJECT_ROOT"
export RESEARCH_CLOUD_RUNTIME="$RUNTIME"
export RESEARCH_CLOUD_MODEL_CACHE="$MODEL_CACHE"

echo
echo "Starting local Qwen server."
echo
echo "Project : $PROJECT_ROOT"
echo "Runtime : $RUNTIME"
echo "Model   : $MODEL"
echo "Cache   : $MODEL_CACHE"
echo "Address : http://$HOST:$PORT"
echo

exec "$LLAMA" server \
    -hf "$MODEL" \
    --host "$HOST" \
    --port "$PORT" \
    --ctx-size "$CTX" \
    --n-gpu-layers auto \
    --fit on \
    --cache-dir "$MODEL_CACHE"
