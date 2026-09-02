#!/usr/bin/env bash

set -e

RUNTIME="/home/seckinozbek/research-cloud-runtime"
LLAMA="$HOME/.llama-app/llama"

MODEL="${QWEN_MODEL:-Qwen/Qwen3-8B-GGUF:Q4_K_M}"
HOST="${QWEN_HOST:-127.0.0.1}"
PORT="${QWEN_PORT:-8080}"
CTX="${QWEN_CTX_SIZE:-8192}"

export LLAMA_CACHE="$RUNTIME/models/llama.cpp"

mkdir -p \
  "$LLAMA_CACHE" \
  "$RUNTIME/logs"

if [ ! -x "$LLAMA" ]; then
    echo "ERROR: llama.cpp launcher not found:"
    echo "$LLAMA"
    exit 1
fi

HTTP_CODE="$(
  curl -s \
    -o /dev/null \
    -w '%{http_code}' \
    "http://${HOST}:${PORT}/health" \
    2>/dev/null || true
)"

if [ "$HTTP_CODE" != "000" ]; then
    echo "A service is already responding on ${HOST}:${PORT}."
    echo "Health HTTP code: ${HTTP_CODE}"
    echo
    echo "If this is the existing DEVOPS QWEN server, leave it running."
    exit 0
fi

echo "DEVOPS QWEN"
echo "============"
echo "Model : $MODEL"
echo "Host  : $HOST"
echo "Port  : $PORT"
echo "Cache : $LLAMA_CACHE"
echo
echo "Press Ctrl+C in this terminal to stop the model server."
echo

exec "$LLAMA" serve \
  -hf "$MODEL" \
  --host "$HOST" \
  --port "$PORT" \
  --ctx-size "$CTX" \
  --n-gpu-layers auto \
  --fit on
