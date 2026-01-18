# Payment tracking bot

A Telegram bot for managing subscription payments with receipt uploads and automatic tracking.

## 🚀 Features

### For Users:
- **💳 Payment Uploads**: Easy receipt upload with automatic processing
- **📊 Status Checking**: Real-time payment status and due dates
- **📅 Payment History**: Track all payment records
- **🔔 Smart Notifications**: Get notified about upcoming payments

### For Admins:
- **👥 Group Management**: Create and manage payment groups
- **👤 User Management**: Add users to groups
- **📈 Statistics**: View payment statistics and overdue users
- **🔍 Monitoring**: Track all payments and user activities

## 🛠 Setup

1. **Clone and Install:**
   ```bash
   git clone <repository>
   cd folder_name
   pip install -r requirements.txt
   ```

2. **Environment Configuration:**
   Copy `.env.example` to `.env` and fill in your values:
   ```bash
   cp .env.example .env
   ```

3. **Database Setup:**
   Create your PostgreSQL database and update the connection details in `.env`

4. **Run the Bot:**
   ```bash
   python main.py
   ```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `TG_TOKEN` | Telegram bot token from BotFather | ✅ |
| `TG_ADMIN_IDS` | Comma-separated list of admin user IDs | ✅ |
| `DB_HOST` | Database host | ✅ |
| `DB_USERNAME` | Database username | ✅ |
| `DB_PASSWORD` | Database password | ✅ |
| `DB_DATABASE` | Database name | ✅ |
| `DB_PORT` | Database port (default: 5432) | ❌ |
| `DB_SSL_MODE` | SSL mode (default: require) | ❌ |
| `BOT_DEFAULT_PAYMENT_PRICE` | Default monthly price | ❌ |
| `BOT_MAX_MONTHS_PAYMENT` | Max months per payment | ❌ |

## 📱 Usage

### User Commands:
- `/start` - Welcome and status overview
- `/pay` - Upload payment receipt
- `/status` - Check payment status
- `/help` - Show help information

### Admin Commands:
- `/admin` - Open admin panel
- Create groups, add users, view statistics

## 🏗 Architecture

```
bot/
├── config/          # Configuration and settings
├── database/        # Database models and operations
├── handlers/        # Command handlers (user & admin)
├── utils/          # Utilities, keyboards, helpers
└── main.py         # Application entry point
```

## 🔒 Security Features

- **Private Chat Only**: All commands work only in private messages
- **Admin Authorization**: Admin commands require user ID verification
- **Input Validation**: All user inputs are validated and sanitized
- **Error Handling**: Comprehensive error handling and logging
- **Database Security**: Prepared statements prevent SQL injection

## 📊 Database Schema

- **users**: User information and registration
- **groups**: Payment groups with due dates
- **payments**: Payment records with receipts
- **user_groups**: User-group associations

## 🚀 Deployment

The bot is designed to work with cloud databases and can be deployed on:
- Heroku
- Railway
- Koyeb
- VPS with Docker

## 📝 License

This project is licensed under the MIT License.

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

---

Built with ❤️ using Python, aiogram 3.x, and PostgreSQL
