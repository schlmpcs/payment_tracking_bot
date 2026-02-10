# Spotify Family Automatization Bot 🎵

A comprehensive Telegram bot for automating Spotify Family plan payments, member tracking, and receipt verification.

## 🚀 Features

### **Member Management**

* **Automatic Registration**: Users join groups via unique invite links.
* **Group Tracking**: Supports multiple family groups (KZ/RU regions).
* **Payment Reminders**: Automated notifications when subscriptions are due.
* **Kick/Ban Logic**: Automatic removal of non-paying members after 3 warnings.

### **Payment Processing**

* **Receipt Upload**: Users upload payment receipts (Photos/PDFs) directly to the bot.
* **Manual Verification**: Admins review and approve/reject payments.
* **Subscription Extension**: Automated extension of "paid until" dates upon approval.
* **Receipt Archiving**: All receipts are forwarded to a private channel for audit.

### **Fraud Detection & Analytics (New! 🕵️‍♀️)**

* **Receipt Parsing**: Automatically extracts "Operation Numbers" from Kaspi receipts (PDFs).
* **Fraud Check (`/fraudcheck`)**:
  * Admins upload a Kaspi statement (Excel/CSV).
  * Bot compares statement operations against database records.
  * **Reports suspicious receipts** (Present in DB but missing from bank statement).
  * **Identifies missing payments** (Present in statement but not in DB).
* **Historical Backfill (`/backfill_receipts`)**: Scans past receipts (starting Feb 2026) to extract operation numbers retrospectively.

## 🛠️ Tech Stack

* **Language**: Python 3.11+
* **Framework**: Aiogram 3.x (Asyncio)
* **Database**: PostgreSQL (via AsyncPG)
* **Deployment**: Docker & Docker Compose
* **Libraries**: `pdfplumber` (PDF parsing), `pandas` (Excel processing)

## 📦 Installation & Deployment

### **Prerequisites**

1. **Docker & Docker Compose** installed.
2. **PostgreSQL** database running (cloud or local).
3. **Telegram Bot Token** from @BotFather.

### **Configuration**

Create a `.env` file in the root directory:

```env
BOT_TOKEN=your_bot_token
ADMIN_IDS=12345678,87654321
DATABASE_URL=postgresql://user:pass@host:5432/dbname
RECEIPT_STORAGE_CHAT_ID=-100xxxxxxxxxx
```

### **Run with Docker (Recommended)**

**1. Build and Run**

```bash
# Build image
docker build -t yourusername/spotify-bot:latest .

# Run container
docker run -d --name spotify-bot --env-file .env --restart unless-stopped yourusername/spotify-bot:latest
```

**2. Using Docker Compose**

```bash
docker-compose up -d --build
```

### **Manual Run**

```bash
pip install -r requirements.txt
python main.py
```

## 📝 Usage Commands

### **User Commands**

* `/start` - Register/Main Menu.
* `/profile` - View subscription status.
* `/pay` - Start payment process (upload receipt).
* `/support` - Contact admin.

### **Admin Commands**

* `/admin` - Admin panel.
* `/stats` - View payment statistics.
* `/broadcast` - Send message to all users.
* `/fraudcheck` - Upload Kaspi statement for reconciliation (KZ only).
* `/backfill_receipts` - Process old receipts for operation numbers.

## 🔐 Database Schema

* **`users`**: Stores Telegram ID, username, group ID.
* **`groups`**: Stores invitelink, cost, region.
* **`payments`**: Stores payment records, receipt file IDs, **operation numbers**.

## 🤝 Contribution

Feel free to fork and submit PRs! Run tests locally before pushing.

---
*Developed by [Your Name]*
