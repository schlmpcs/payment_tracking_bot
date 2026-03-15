#!/bin/bash
# Runs backup_db.sh once daily at 03:00 AM (container time)
# Designed to run as a long-lived Docker service

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "[backup-cron] Service started at $(date)"

while true; do
  # Seconds until next 03:00 AM
  now=$(date +%s)
  next=$(date -d 'tomorrow 03:00' +%s)
  sleep_secs=$((next - now))

  echo "[backup-cron] Next backup at $(date -d "@$next") (sleeping ${sleep_secs}s)"
  sleep "$sleep_secs"

  bash "$SCRIPT_DIR/backup_db.sh" || echo "[backup-cron] backup_db.sh exited with error"
done
