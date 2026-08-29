#!/usr/bin/env bash
set -euo pipefail

SESSION="${TMUX_SESSION:-research-cloud}"
PROMETHEUS_URL="${PROMETHEUS_URL:-http://127.0.0.1:9090}"
STATE_DIR="metadata/monitoring"
STATE_FILE="$STATE_DIR/active_alerts.txt"

mkdir -p "$STATE_DIR"
touch "$STATE_FILE"

echo "[alert-watcher] Watching Prometheus every 5 seconds..."
echo "[alert-watcher] Endpoint: $PROMETHEUS_URL/api/v1/alerts"

connected=false

while true; do
  RESPONSE="$(curl -fsS "$PROMETHEUS_URL/api/v1/alerts" 2>/dev/null || true)"

  if [ -z "$RESPONSE" ]; then
    if [ "$connected" = "true" ]; then
      echo "[alert-watcher] ⚠️ Prometheus connection lost; retrying..."
    else
      echo "[alert-watcher] Prometheus unavailable; retrying..."
    fi
    connected=false
    sleep 5
    continue
  fi

  if [ "$connected" = "false" ]; then
    echo "[alert-watcher] ✅ Prometheus connected."
    echo "[alert-watcher] ✅ Alert watcher active."
    connected=true
  fi

  printf '%s' "$RESPONSE" | python3 -c '
import json
import sys

data = json.load(sys.stdin)

for alert in data.get("data", {}).get("alerts", []):
    if alert.get("state") != "firing":
        continue

    labels = alert.get("labels", {})
    annotations = alert.get("annotations", {})

    name = labels.get("alertname", "unknown")
    severity = labels.get("severity", "unknown")
    summary = annotations.get("summary", "")

    print(f"{name}\t{severity}\t{summary}")
' > "$STATE_FILE.new"

  cut -f1 "$STATE_FILE" 2>/dev/null | sort -u > "$STATE_FILE.old.names"
  cut -f1 "$STATE_FILE.new" 2>/dev/null | sort -u > "$STATE_FILE.new.names"

  while IFS=$'\t' read -r name severity summary; do
    [ -z "$name" ] && continue

    if ! grep -qxF "$name" "$STATE_FILE.old.names"; then
      echo
      echo "============================================================"
      echo "🚨 FIRING ALERT: $name"
      echo "Severity: $severity"
      echo "$summary"
      echo "============================================================"
      echo

      if tmux has-session -t "$SESSION" 2>/dev/null; then
        tmux display-message -d 10000 \
          "🚨 ALERT: $name [$severity] — $summary" || true

        tmux select-window -t "$SESSION:alerts" 2>/dev/null || true
      fi
    fi
  done < "$STATE_FILE.new"

  while IFS= read -r name; do
    [ -z "$name" ] && continue

    if ! grep -qxF "$name" "$STATE_FILE.new.names"; then
      echo
      echo "✅ RESOLVED: $name"
      echo

      if tmux has-session -t "$SESSION" 2>/dev/null; then
        tmux display-message -d 8000 \
          "✅ RESOLVED: $name" || true
      fi
    fi
  done < "$STATE_FILE.old.names"

  mv "$STATE_FILE.new" "$STATE_FILE"
  rm -f "$STATE_FILE.old.names" "$STATE_FILE.new.names"

  sleep 5
done
