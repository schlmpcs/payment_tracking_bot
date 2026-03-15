#!/bin/bash
# Sets up a daily cron job to run backup_db.sh at 3:00 AM server time
# Run once on the server: bash scripts/setup_backup_cron.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKUP_SCRIPT="$SCRIPT_DIR/backup_db.sh"
LOG_FILE="$(dirname "$SCRIPT_DIR")/backups/cron.log"
CRON_JOB="0 3 * * * bash $BACKUP_SCRIPT >> $LOG_FILE 2>&1"

# Install postgresql-client if pg_dump is missing
if ! command -v pg_dump &>/dev/null; then
  echo "[setup] pg_dump not found — installing postgresql-client..."
  apt-get update -qq && apt-get install -y postgresql-client
fi

chmod +x "$BACKUP_SCRIPT"

# Add cron job only if not already present
if crontab -l 2>/dev/null | grep -qF "$BACKUP_SCRIPT"; then
  echo "[setup] Cron job already exists, skipping."
else
  (crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -
  echo "[setup] Cron job added: $CRON_JOB"
fi

mkdir -p "$(dirname "$LOG_FILE")"
echo "[setup] Backup cron configured. Backups will run daily at 3:00 AM."
echo "[setup] Backup script: $BACKUP_SCRIPT"
echo "[setup] Cron log:      $LOG_FILE"
echo "[setup] Backups dir:   $(dirname "$SCRIPT_DIR")/backups/"
