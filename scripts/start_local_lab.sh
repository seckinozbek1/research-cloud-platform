#!/usr/bin/env bash
set -euo pipefail

SESSION="research-cloud"
ROOT="$HOME/research-cloud-platform"

echo "Running interactive preflight..."
sudo -v
echo "Sudo authentication ready."

if tmux has-session -t "$SESSION" 2>/dev/null; then
  echo "tmux session '$SESSION' already exists."
  echo "Attach with: tmux attach -t $SESSION"
  exit 0
fi

tmux new-session -d -s "$SESSION" -n infra -c "$ROOT"
tmux send-keys -t "$SESSION:infra" \
  'sudo cloud-provider-kind --enable-lb-port-mapping' C-m

tmux new-window -t "$SESSION" -n api -c "$ROOT"
tmux send-keys -t "$SESSION:api" \
  'source .venv/bin/activate && uvicorn src.api:app --host 127.0.0.1 --port 8001' C-m

tmux new-window -t "$SESSION" -n prometheus -c "$ROOT"
tmux send-keys -t "$SESSION:prometheus" \
  'docker run --rm --name research-prometheus --network host -v "$PWD/monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro" prom/prometheus:latest' C-m

tmux new-window -t "$SESSION" -n grafana -c "$ROOT"
tmux send-keys -t "$SESSION:grafana" \
  'docker run --rm --name research-grafana --network host grafana/grafana:latest' C-m

tmux new-window -t "$SESSION" -n client -c "$ROOT"
tmux send-keys -t "$SESSION:client" \
  'source .venv/bin/activate' C-m

tmux new-window -t "$SESSION" -n work -c "$ROOT"
tmux send-keys -t "$SESSION:work" \
  'source .venv/bin/activate' C-m

tmux select-window -t "$SESSION:work"

echo "Started tmux session: $SESSION"
echo "Attach with: tmux attach -t $SESSION"
