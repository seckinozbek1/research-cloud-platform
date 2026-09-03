#!/usr/bin/env bash

# This script must be sourced so that environment variables and
# virtual-environment activation remain in the caller's shell.
#
# Usage:
#   source scripts/enter_runtime.sh

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    echo "This script must be sourced, not executed."
    echo
    echo "Use:"
    echo "  source scripts/enter_runtime.sh"
    exit 2
fi

set -e

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

VENV="${RESEARCH_CLOUD_VENV:-$RUNTIME/venv}"

if [[ ! -f "$VENV/bin/activate" ]]; then
    echo "Runtime virtual environment not found:"
    echo "  $VENV"
    echo
    echo "Set RESEARCH_CLOUD_RUNTIME or RESEARCH_CLOUD_VENV"
    echo "to the installation-specific location."
    return 2
fi

cd "$PROJECT_ROOT"

# shellcheck disable=SC1090
source "$VENV/bin/activate"

export RESEARCH_CLOUD_PROJECT_ROOT="$PROJECT_ROOT"
export RESEARCH_CLOUD_RUNTIME="$RUNTIME"

export TMPDIR="${TMPDIR:-$RUNTIME/tmp}"
export XDG_CACHE_HOME="${XDG_CACHE_HOME:-$RUNTIME/cache}"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-$RUNTIME/pip-cache}"

export SPARK_LOCAL_DIRS="${SPARK_LOCAL_DIRS:-$RUNTIME/spark}"
export RAY_TMPDIR="${RAY_TMPDIR:-$RUNTIME/ray}"

export TORCH_HOME="${TORCH_HOME:-$RUNTIME/torch}"

export MLFLOW_TRACKING_URI="${MLFLOW_TRACKING_URI:-sqlite:///$RUNTIME/mlflow/mlflow.db}"

export MLFLOW_ARTIFACT_ROOT="${MLFLOW_ARTIFACT_ROOT:-$RUNTIME/mlflow/artifacts}"

mkdir -p \
    "$TMPDIR" \
    "$XDG_CACHE_HOME" \
    "$PIP_CACHE_DIR" \
    "$SPARK_LOCAL_DIRS" \
    "$RAY_TMPDIR" \
    "$TORCH_HOME" \
    "$RUNTIME/mlflow/artifacts" \
    "$RUNTIME/intermediate" \
    "$RUNTIME/scratch" \
    "$RUNTIME/agent-managed"

echo
echo "Research Cloud runtime ready."
echo
echo "Source repo : $RESEARCH_CLOUD_PROJECT_ROOT"
echo "Runtime     : $RESEARCH_CLOUD_RUNTIME"
echo "Python      : $(which python)"
echo
