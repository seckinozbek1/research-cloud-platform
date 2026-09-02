#!/usr/bin/env bash

set -e

REPO="/mnt/c/Users/secki/local/research-cloud-platform"
RUNTIME="/home/seckinozbek/research-cloud-runtime"

cd "$REPO"

source "$RUNTIME/venv/bin/activate"

export RESEARCH_CLOUD_REPO="$REPO"
export RESEARCH_CLOUD_RUNTIME="$RUNTIME"

export TMPDIR="$RUNTIME/tmp"
export XDG_CACHE_HOME="$RUNTIME/cache"
export PIP_CACHE_DIR="$RUNTIME/pip-cache"

export SPARK_LOCAL_DIRS="$RUNTIME/spark"
export RAY_TMPDIR="$RUNTIME/ray"

export TORCH_HOME="$RUNTIME/torch"

export MLFLOW_TRACKING_URI="sqlite:///$RUNTIME/mlflow/mlflow.db"
export MLFLOW_ARTIFACT_ROOT="$RUNTIME/mlflow/artifacts"

mkdir -p \
  "$TMPDIR" \
  "$XDG_CACHE_HOME" \
  "$PIP_CACHE_DIR" \
  "$SPARK_LOCAL_DIRS" \
  "$RAY_TMPDIR" \
  "$TORCH_HOME" \
  "$RUNTIME/mlflow/artifacts" \
  "$RUNTIME/intermediate" \
  "$RUNTIME/scratch"

echo
echo "Research Cloud runtime ready."
echo
echo "Source repo : $RESEARCH_CLOUD_REPO"
echo "Runtime     : $RESEARCH_CLOUD_RUNTIME"
echo "Python      : $(which python)"
echo

exec bash --norc
