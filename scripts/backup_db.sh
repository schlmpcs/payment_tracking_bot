#!/bin/bash
# Daily PostgreSQL backup script
# Reads DB credentials from .env and saves compressed dumps with 7-day retention
# Sends a Telegram message to all admins after each run (success or failure)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$PROJECT_DIR/.env"
BACKUP_DIR="$PROJECT_DIR/backups"
RETENTION_DAYS=7

# Load .env variables
if [[ ! -f "$ENV_FILE" ]]; then
  echo "[backup] ERROR: .env file not found at $ENV_FILE"
  exit 1
fi

export $(grep -v '^#' "$ENV_FILE" | grep -v '^$' | xargs)

# Validate required variables
for var in DB_HOST DB_PORT DB_USERNAME DB_PASSWORD DB_DATABASE TG_TOKEN TG_ADMIN_IDS; do
  if [[ -z "${!var:-}" ]]; then
    echo "[backup] ERROR: $var is not set in .env"
    exit 1
  fi
done

# Send a message to every admin ID via Telegram Bot API
# TG_ADMIN_IDS can be "[123, 456]" or "123" — strip brackets and split on commas
tg_notify() {
  local message="$1"
  local ids
  ids=$(echo "$TG_ADMIN_IDS" | tr -d '[] ' | tr ',' '\n')
  while IFS= read -r chat_id; do
    [[ -z "$chat_id" ]] && continue
    curl -s -X POST "https://api.telegram.org/bot${TG_TOKEN}/sendMessage" \
      --data-urlencode "chat_id=${chat_id}" \
      --data-urlencode "text=${message}" \
      --data-urlencode "parse_mode=HTML" \
      > /dev/null
  done <<< "$ids"
}

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_FILE="$BACKUP_DIR/${DB_DATABASE}_${TIMESTAMP}.sql.gz"

echo "[backup] Starting backup of $DB_DATABASE at $(date)"

# Run pg_dump — on failure notify admins and exit
PGSSLMODE="${DB_SSL_MODE:-disable}"
export PGPASSWORD="$DB_PASSWORD"

if ! pg_dump \
  --host="$DB_HOST" \
  --port="$DB_PORT" \
  --username="$DB_USERNAME" \
  --dbname="$DB_DATABASE" \
  --no-password \
  --format=plain \
  --verbose \
  2>>"$BACKUP_DIR/backup.log" \
  | gzip > "$BACKUP_FILE"; then
  tg_notify $'<b>Backup FAILED</b>\nDatabase: '"$DB_DATABASE"$'\nTime: '"$(date)"
  echo "[backup] FAILED at $(date)"
  exit 1
fi

FILE_SIZE=$(du -sh "$BACKUP_FILE" | cut -f1)
echo "[backup] Backup saved: $BACKUP_FILE ($FILE_SIZE)"

# Remove backups older than RETENTION_DAYS
find "$BACKUP_DIR" -name "${DB_DATABASE}_*.sql.gz" -mtime +$RETENTION_DAYS -delete
echo "[backup] Cleaned up backups older than $RETENTION_DAYS days"

# Count remaining backups
BACKUP_COUNT=$(find "$BACKUP_DIR" -name "${DB_DATABASE}_*.sql.gz" | wc -l | tr -d ' ')

tg_notify "<b>Backup complete</b>
Database: ${DB_DATABASE}
File: ${DB_DATABASE}_${TIMESTAMP}.sql.gz
Size: ${FILE_SIZE}
Retained backups: ${BACKUP_COUNT}/${RETENTION_DAYS}
Time: $(date)"

echo "[backup] Done at $(date)"
