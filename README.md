# Spotify Family Automatization Bot

A Telegram bot for automating Spotify Family plan payments, member tracking, and receipt verification.

## Features

### Member Management

- Automatic registration via unique invite links
- Multiple family groups (KZ/RU regions)
- Automated payment reminders when subscriptions are due
- Automatic removal of non-paying members after 3 warnings

### Payment Processing

- Users upload payment receipts (photos/PDFs) directly to the bot
- Admins review and approve/reject payments
- Automated subscription extension upon approval
- All receipts forwarded to a private channel for audit

### Fraud Detection & Analytics

- Automatically extracts operation numbers from Kaspi receipts (PDFs)
- `/fraudcheck` — admins upload a Kaspi statement (Excel/CSV); bot cross-references against DB records and reports mismatches
- `/backfill_receipts` — retroactively extracts operation numbers from past receipts

### Daily Database Backups

- Automatic `pg_dump` runs at 3:00 AM daily inside the `backup` Docker service
- Compressed `.sql.gz` files saved to `backups/` on the server
- 7-day retention (older dumps deleted automatically)
- Admin receives a Telegram message after every backup (success or failure)

## Tech Stack

- **Language**: Python 3.11+
- **Framework**: Aiogram 3.x (async)
- **Database**: PostgreSQL (via AsyncPG)
- **Deployment**: Docker & Docker Compose
- **Libraries**: `pdfplumber` (PDF parsing), `pandas` (Excel processing)

## Configuration

Copy `.env.example` to `.env` and fill in all values:

```env
# Telegram
TG_TOKEN=your_bot_token
TG_ADMIN_IDS=[123456789, 987654321]
TG_RECEIPT_STORAGE_CHAT_ID=123456789

# Database
DB_HOST=your_database_host
DB_PORT=5432
DB_USERNAME=your_database_username
DB_PASSWORD=your_database_password
DB_DATABASE=your_database_name
DB_SSL_MODE=require
```

## Deployment

### First-time server setup

```bash
# Clone repo
git clone https://github.com/your-username/your-repo.git
cd your-repo

# Create .env on the server
nano .env

# Install Docker if needed
curl -fsSL https://get.docker.com | sh
```

### Deploy / update

On the server:

```bash
bash deploy.sh
```

This pulls the latest code, rebuilds both containers, removes dangling images, and tails logs.

The `backup` service starts automatically alongside the bot and runs the daily backup at 3:00 AM.

### Manually trigger a backup

```bash
docker compose exec backup bash /app/scripts/backup_db.sh
```

### Check backup logs

```bash
docker compose logs backup
ls -lh backups/
```

## Commands

### User

| Command | Description |
| ------- | ----------- |
| `/start` | Register / main menu |
| `/profile` | View subscription status |
| `/pay` | Upload payment receipt |
| `/support` | Contact admin |

### Admin

| Command | Description |
| ------- | ----------- |
| `/admin` | Admin panel |
| `/stats` | Payment statistics |
| `/broadcast` | Message all users |
| `/fraudcheck` | Reconcile Kaspi statement against DB |
| `/backfill_receipts` | Process old receipts for operation numbers |

## Database Schema

| Table | Description |
| ----- | ----------- |
| `users` | Telegram ID, username, display ID |
| `groups` | Group name, payment day, next payment date |
| `payments` | Payment records, receipt file IDs, operation numbers |
| `user_groups` | User↔group membership with slot and phantom support |
