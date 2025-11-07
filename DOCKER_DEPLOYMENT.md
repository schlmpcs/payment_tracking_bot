# 🚀 Digital Ocean Docker Deployment Guide

## Overview
This guide will show you how to deploy the Spotify Family Payment Bot using Docker on Digital Ocean. Docker makes deployment much easier and more reliable.

## Prerequisites
- Digital Ocean account with payment method
- Your bot's .env configuration ready

## Step 1: Create Digital Ocean Droplet

### 1.1 Create Droplet
1. Go to [Digital Ocean Console](https://cloud.digitalocean.com)
2. Click **"Create"** → **"Droplets"**

### 1.2 Choose Configuration
**Recommended Settings:**
- **Image**: Ubuntu 22.04 LTS
- **Plan**: Basic
  - **Size**: $12/month (2 vCPU, 2 GB RAM, 50 GB SSD) - recommended for production
  - **Alternative**: $6/month (1 vCPU, 1 GB RAM, 25 GB SSD) - minimum for testing
- **Region**: Choose closest to your users
- **VPC**: Default
- **Authentication**: SSH Key (strongly recommended)
- **Monitoring**: Enable (optional but helpful)
- **Hostname**: `spotify-bot-production`

### 1.3 SSH Key Setup (If you don't have one)
**On Windows (PowerShell):**
```powershell
# Generate SSH key
ssh-keygen -t ed25519 -C "your-email@example.com"

# Copy public key
Get-Content ~/.ssh/id_ed25519.pub | Set-Clipboard
```

**On macOS/Linux:**
```bash
# Generate SSH key
ssh-keygen -t ed25519 -C "your-email@example.com"

# Copy public key
cat ~/.ssh/id_ed25519.pub
```

Paste the public key into Digital Ocean's SSH Key field.

## Step 2: Connect to Your Droplet

### 2.1 Get Connection Info
After droplet creation, note the IP address (e.g., `164.92.xxx.xxx`)

### 2.2 Connect via SSH
```bash
ssh root@YOUR_DROPLET_IP    
```

## Step 3: Install Docker (One-Time Setup)

### 3.1 Update System
```bash
apt update && apt upgrade -y
```

### 3.2 Install Docker
```bash
# Install Docker using official script
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Add current user to docker group (optional)
usermod -aG docker root

# Start and enable Docker
systemctl start docker
systemctl enable docker

# Install Docker Compose
apt install -y docker-compose

# Verify installation
docker --version
docker-compose --version
```

### 3.3 Install Git
```bash
apt install -y git
```

## Step 4: Deploy Your Bot

### 4.1 Clone Repository
```bash
cd /opt
git clone https://github.com/wstoccob/spotify_family_automatization.git
cd spotify_family_automatization
```

### 4.2 Configure Environment
```bash
# Copy example env file
cp .env.example .env

# Edit with your settings
nano .env
```

**Paste your configuration:**
```env
# Telegram Bot Configuration
TG_TOKEN=8300050171:AAFEUS_SJKf_ZR65dR_gX63_u_K38tuW67A
TG_ADMIN_IDS=[911203828, 470198003]
TG_RECEIPT_STORAGE_CHAT_ID=911203828

# Database Configuration
DB_HOST=ep-sparkling-heart-a2qz7o0g.eu-central-1.pg.koyeb.app
DB_PORT=5432
DB_USERNAME=koyeb-adm
DB_PASSWORD=npg_7XKUDliuHZ2R
DB_DATABASE=koyebdb
DB_SSL_MODE=require

# Bot Settings (Optional)
BOT_DEFAULT_PAYMENT_PRICE=5.99
BOT_MAX_MONTHS_PAYMENT=6
BOT_PAYMENT_REMINDER_DAYS=3
```

Save with `Ctrl+X`, `Y`, `Enter`

### 4.3 Build and Run Bot
```bash
# Build the Docker image
docker build -t spotify-bot .

# Run the bot
docker run -d \
  --name spotify-bot \
  --restart unless-stopped \
  --env-file .env \
  spotify-bot

# Check if it's running
docker ps
```

### 4.4 View Logs
```bash
# View real-time logs
docker logs -f spotify-bot

# View recent logs
docker logs --tail 50 spotify-bot
```

## Step 5: Set Up Automatic Restart (Production)

### 5.1 Create Systemd Service (Optional but Recommended)
```bash
cat > /etc/systemd/system/spotify-bot.service << 'EOF'
[Unit]
Description=Spotify Bot Docker Container
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/opt/spotify_family_automatization
ExecStart=/usr/bin/docker start spotify-bot
ExecStop=/usr/bin/docker stop spotify-bot
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
EOF

# Enable the service
systemctl enable spotify-bot
```

## Step 6: Management Commands

### 6.1 Basic Docker Commands
```bash
# View running containers
docker ps

# View all containers (including stopped)
docker ps -a

# Stop the bot
docker stop spotify-bot

# Start the bot
docker start spotify-bot

# Restart the bot
docker restart spotify-bot

# View logs
docker logs spotify-bot

# View real-time logs
docker logs -f spotify-bot

# Remove container (if you need to recreate)
docker rm spotify-bot
```

### 6.2 Update Bot (When you push changes to GitHub)
```bash
cd /opt/spotify_family_automatization

# Stop current container
docker stop spotify-bot
docker rm spotify-bot

# Pull latest code
git pull origin main

# Rebuild image
docker build -t spotify-bot .

# Run new container
docker run -d \
  --name spotify-bot \
  --restart unless-stopped \
  --env-file .env \
  spotify-bot

# Check logs
docker logs -f spotify-bot
```

## Step 7: Security Setup

### 7.1 Configure Firewall
```bash
# Install UFW if not installed
apt install -y ufw

# Allow SSH
ufw allow ssh

# Allow HTTPS (for webhooks if needed later)
ufw allow 443

# Enable firewall
ufw --force enable

# Check status
ufw status
```

### 7.2 Secure SSH
```bash
# Edit SSH config
nano /etc/ssh/sshd_config
```

Change these settings:
```
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
```

```bash
# Create non-root user
adduser deploy
usermod -aG sudo deploy
usermod -aG docker deploy

# Copy SSH key to new user
mkdir -p /home/deploy/.ssh
cp /root/.ssh/authorized_keys /home/deploy/.ssh/
chown -R deploy:deploy /home/deploy/.ssh
chmod 700 /home/deploy/.ssh
chmod 600 /home/deploy/.ssh/authorized_keys

# Restart SSH
systemctl restart ssh
```

**From now on, connect as:** `ssh deploy@YOUR_DROPLET_IP`

## Step 8: Monitoring and Maintenance

### 8.1 Health Checks
```bash
# Check if bot is running
docker ps | grep spotify-bot

# Check Docker service status
systemctl status docker

# Check system resources
htop
df -h
```

### 8.2 Backup Strategy
```bash
# Create backup script
cat > /opt/backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="/opt/backups"
mkdir -p $BACKUP_DIR

# Backup bot configuration and code
tar -czf $BACKUP_DIR/spotify_bot_$DATE.tar.gz /opt/spotify_family_automatization

# Keep only last 7 days of backups
find $BACKUP_DIR -name "spotify_bot_*.tar.gz" -mtime +7 -delete

echo "Backup completed: spotify_bot_$DATE.tar.gz"
EOF

chmod +x /opt/backup.sh

# Add to crontab for daily backups
echo "0 3 * * * /opt/backup.sh" | crontab -
```

## Step 9: Alternative Deployment Methods

### 9.1 Using Docker Compose (Easier for updates)
```bash
# Use docker-compose for easier management
cd /opt/spotify_family_automatization

# Start with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f

# Stop
docker-compose down

# Update and restart
git pull origin main
docker-compose build
docker-compose up -d
```

### 9.2 Using Docker Hub (Advanced)
You can also push your image to Docker Hub and pull it on the server:

```bash
# On your local machine (optional)
docker build -t yourusername/spotify-bot .
docker push yourusername/spotify-bot

# On the server
docker pull yourusername/spotify-bot
docker run -d --name spotify-bot --restart unless-stopped --env-file .env yourusername/spotify-bot
```

## 🎉 Deployment Complete!

### Quick Health Check:
1. **Check container status:** `docker ps`
2. **View logs:** `docker logs spotify-bot`
3. **Test bot in Telegram:** Send `/start`
4. **Test admin features:** Send `/admin`
5. **Test payment flow:** Send `/pay`
6. **Test Excel import:** Upload Excel file via `/admin`

### Costs:
- **Droplet**: $12/month (recommended) or $6/month (minimum)
- **Database**: Your existing Koyeb cost
- **Total**: ~$12-18/month

### Benefits of Docker Deployment:
- ✅ **Consistent environment** - works the same everywhere
- ✅ **Easy updates** - just rebuild and restart
- ✅ **Isolation** - bot runs in its own container
- ✅ **Automatic restarts** - container restarts if it crashes
- ✅ **Easy rollback** - keep previous images for quick rollback
- ✅ **Scalable** - easy to add more instances later

Your bot is now running in production with Docker! 🐳🤖