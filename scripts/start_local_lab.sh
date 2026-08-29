#!/usr/bin/env bash
set -euo pipefail

SESSION="research-cloud"
ROOT="$HOME/research-cloud-platform"

log() {
  printf '[local-lab] %s\n' "$1"
}

fail() {
  printf '[local-lab] ERROR: %s\n' "$1" >&2
  exit 1
}

wait_for_url() {
  local name="$1"
  local url="$2"
  local attempts="${3:-30}"

  log "Waiting for $name..."

  for ((i=1; i<=attempts; i++)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      log "$name is ready."
      return 0
    fi
    sleep 1
  done

  fail "$name did not become ready at $url"
}

open_browser() {
  local url="$1"

  if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command \
      "Start-Process '$url'" >/dev/null 2>&1 &
    return 0
  fi

  if command -v wslview >/dev/null 2>&1; then
    wslview "$url" >/dev/null 2>&1 &
    return 0
  fi

  log "Could not open a browser automatically."
  log "Open manually: $url"
}

cleanup_lab_container() {
  local name="$1"

  if docker ps -a --format '{{.Names}}' | grep -qx "$name"; then
    log "Removing stale lab container: $name"
    docker rm -f "$name" >/dev/null
  fi
}

cd "$ROOT"

log "Running interactive preflight."

# Keep authentication visible instead of leaving sudo waiting
# inside a background tmux window.
sudo -v

if tmux has-session -t "$SESSION" 2>/dev/null; then
  log "Session '$SESSION' already exists."
  log "Attaching to the existing session."
  exec tmux attach -t "$SESSION"
fi

# These names belong exclusively to this local lab.
# Remove stale instances left by an earlier manual/failed run.
cleanup_lab_container "research-prometheus"
cleanup_lab_container "research-grafana"

log "Creating tmux session."

tmux new-session -d -s "$SESSION" -n infra -c "$ROOT"
tmux send-keys -t "$SESSION:infra" \
  'sudo cloud-provider-kind --enable-lb-port-mapping' C-m

tmux new-window -t "$SESSION" -n api -c "$ROOT"
tmux send-keys -t "$SESSION:api" \
  'source .venv/bin/activate && uvicorn src.api:app --host 127.0.0.1 --port 8001' C-m

tmux new-window -t "$SESSION" -n prometheus -c "$ROOT"
tmux send-keys -t "$SESSION:prometheus" \
  'docker run --rm --name research-prometheus --network host -v "$PWD/monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro" -v "$PWD/monitoring/alerts.yml:/etc/prometheus/alerts.yml:ro" prom/prometheus:latest' C-m

tmux new-window -t "$SESSION" -n grafana -c "$ROOT"
tmux send-keys -t "$SESSION:grafana" \
  'docker run --rm --name research-grafana --env-file "$PWD/environment/local_secrets.env" -e GF_AUTH_ANONYMOUS_ENABLED=true -e GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer -e GF_AUTH_ANONYMOUS_ORG_NAME="Main Org." --add-host=host.docker.internal:host-gateway -p 127.0.0.1:3000:3000 -v "$PWD/monitoring/grafana/provisioning:/etc/grafana/provisioning:ro" -v "$PWD/monitoring/grafana/dashboards:/var/lib/grafana/dashboards:ro" grafana/grafana:latest' C-m

tmux new-window -t "$SESSION" -n alerts -c "$ROOT"
tmux send-keys -t "$SESSION:alerts"   './scripts/alert_watcher.sh' C-m

tmux new-window -t "$SESSION" -n client -c "$ROOT"
tmux send-keys -t "$SESSION:client" \
  'source .venv/bin/activate' C-m

tmux new-window -t "$SESSION" -n work -c "$ROOT"
tmux send-keys -t "$SESSION:work" \
  'source .venv/bin/activate' C-m

tmux select-window -t "$SESSION:work"

wait_for_url "API" "http://127.0.0.1:8001/health"
wait_for_url "Prometheus" "http://127.0.0.1:9090/-/healthy"
wait_for_url "Grafana" "http://127.0.0.1:3000/api/health"

log "Checking Grafana from the Windows side..."

if command -v powershell.exe >/dev/null 2>&1; then
  windows_ready=false

  for i in {1..30}; do
    if powershell.exe -NoProfile -Command       "try { Invoke-WebRequest -UseBasicParsing -Uri 'http://127.0.0.1:3000/api/health' -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }"       >/dev/null 2>&1; then
      windows_ready=true
      break
    fi
    sleep 1
  done

  if [ "$windows_ready" != "true" ]; then
    fail "Grafana is healthy inside WSL but is not reachable from Windows on http://127.0.0.1:3000"
  fi
fi

log "Local lab is ready."
log "Opening Grafana dashboard in your browser."

open_browser "http://127.0.0.1:3000/d/research-cloud-api/research-cloud-api"

log "Attaching to tmux session '$SESSION'."
exec tmux attach -t "$SESSION"
