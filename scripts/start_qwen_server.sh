#!/usr/bin/env bash

set -u
set -o pipefail

SCRIPT_DIR="$(
    cd -- "$(dirname -- "${BASH_SOURCE[0]}")" 2>/dev/null &&
    pwd
)"

PROJECT_ROOT="${RESEARCH_CLOUD_PROJECT_ROOT:-$(
    cd -- "${SCRIPT_DIR}/.." 2>/dev/null &&
    pwd
)}"

if [[ -n "${RESEARCH_CLOUD_RUNTIME:-}" ]]; then
    RUNTIME="$RESEARCH_CLOUD_RUNTIME"
elif [[ -d "$HOME/research-cloud-runtime" ]]; then
    RUNTIME="$HOME/research-cloud-runtime"
elif [[ "$(uname -s)" == "Darwin" ]]; then
    RUNTIME="$HOME/Library/Application Support/research-cloud-platform"
else
    RUNTIME="${XDG_DATA_HOME:-$HOME/.local/share}/research-cloud-platform"
fi

HOST="${QWEN_HOST:-127.0.0.1}"
PORT="${QWEN_PORT:-8080}"
CTX="${QWEN_CTX:-8192}"

MODEL_FILE="${QWEN_MODEL_FILE:-}"

if [[ -z "$MODEL_FILE" ]]; then
    HF_ROOT="$RUNTIME/cache/huggingface/hub/models--Qwen--Qwen3-8B-GGUF/snapshots"

    if [[ -d "$HF_ROOT" ]]; then
        MODEL_FILE="$(
            find "$HF_ROOT" \
                \( -type f -o -type l \) \
                -name 'Qwen3-8B-Q4_K_M.gguf' \
                -print \
                -quit 2>/dev/null
        )"
    fi
fi

if [[ -z "$MODEL_FILE" || ! -e "$MODEL_FILE" ]]; then
    echo "ERROR: Local Qwen model was not found."
    echo
    echo "Expected:"
    echo "  QWEN_MODEL_FILE=<path-to-Qwen3-8B-Q4_K_M.gguf>"
    echo
    echo "or a cached model under:"
    echo "  $RUNTIME/cache/huggingface/hub/"
    echo
    echo "Automatic model download is intentionally disabled."
    exit 1
fi

if [[ -n "${LLAMA_BIN:-}" && -x "${LLAMA_BIN}" ]]; then
    LLAMA="$LLAMA_BIN"
elif command -v llama >/dev/null 2>&1; then
    LLAMA="$(command -v llama)"
elif [[ -x "$HOME/.llama-app/llama" ]]; then
    LLAMA="$HOME/.llama-app/llama"
else
    echo "ERROR: llama.cpp launcher was not found."
    echo "Set LLAMA_BIN to the llama executable."
    exit 2
fi

if command -v curl >/dev/null 2>&1; then
    if curl \
        --silent \
        --fail \
        --max-time 2 \
        "http://${HOST}:${PORT}/health" \
        >/dev/null 2>&1
    then
        echo "Qwen server is already ready at:"
        echo "  http://${HOST}:${PORT}"
        exit 0
    fi
fi

export RESEARCH_CLOUD_PROJECT_ROOT="$PROJECT_ROOT"
export RESEARCH_CLOUD_RUNTIME="$RUNTIME"

echo
echo "Starting local Qwen server."
echo
echo "Project : $PROJECT_ROOT"
echo "Runtime : $RUNTIME"
echo "Model   : $MODEL_FILE"
echo "Address : http://${HOST}:${PORT}"
echo

exec "$LLAMA" server \
    -m "$MODEL_FILE" \
    --host "$HOST" \
    --port "$PORT" \
    --ctx-size "$CTX" \
    --n-gpu-layers auto \
    --fit on
