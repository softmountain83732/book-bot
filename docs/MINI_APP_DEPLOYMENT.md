# HBTU Book Marketplace — Telegram Mini App Deployment Guide

This guide documents the production deployment of the **HBTU Book Marketplace Telegram Mini App** on an Ubuntu/Debian Linux VPS using **PM2** and **Nginx**.

---

## 1. Architecture Overview

The system runs as two concurrent, isolated processes sharing a single MongoDB database:

```
                  +-----------------------------------+
                  |      User / Telegram Client       |
                  +-----------------+-----------------+
                                    |
                    +---------------+---------------+
                    |                               |
          Telegram Bot Commands             Mini App Webview
                    |                               |
                    v                               v
             +--------------+               +---------------+
             | PM2 Process  |               |  Nginx (443)  |
             |my-python-app |               +-------+-------+
             | (Long Polling)                       |
             +-------+------+          +------------+------------+
                     |                 |                         |
                     |          Static Frontend            FastAPI Proxy
                     |         (/root/.../dist)          (http://127.0.0.1:8000)
                     |                 |                         |
                     |                 |                  +------+------+
                     |                 |                  | PM2 Process |
                     |                 |                  |  book-api   |
                     |                 |                  +------+------+
                     v                 v                         v
               +---------------------------------------------------+
               |               MongoDB Database                    |
               +---------------------------------------------------+
```

- **`my-python-app`**: The existing Telegram Bot process running long-polling via `python-telegram-bot` (unaltered).
- **`book-api`**: FastAPI service running under Uvicorn on `127.0.0.1:8000`.
- **Frontend**: Single-page application built with React + Vite, served as static files by Nginx.

---

## 2. Server Prerequisites

Ensure the following tools and runtimes are installed on the VPS:
- **Python**: `>= 3.11`
- **Node.js**: `>= 18.x` and **npm**
- **MongoDB**: `>= 6.0` (running locally or remote URI)
- **PM2**: Global process manager (`npm install -g pm2`)
- **Nginx**: Web server with SSL support (`certbot`)

---

## 3. Installation & Build

### Step 1: Update Python Dependencies
In the repository root (`/root/bookbot`):
```bash
cd /root/bookbot
source venv/bin/activate
pip install -r requirements.txt
```

### Step 2: Build the Frontend
```bash
cd /root/bookbot/frontend
npm ci
npm run build
```
The static assets will be compiled into `/root/bookbot/frontend/dist/`.

---

## 4. Environment Configuration

Verify `/root/bookbot/.env` contains the required keys:

```dotenv
# Telegram Bot
BOT_TOKEN=your_bot_token_here
BOT_USERNAME=hbtu_books_bot

# MongoDB
MONGODB_URI=mongodb://127.0.0.1:27017
DATABASE_NAME=hbtu_book_marketplace

# Channel
CHANNEL_ID=-1001234567890
CHANNEL_JOIN_URL=https://t.me/your_channel_invite

# Admin Privileges
ADMIN_IDS=123456789,987654321

# Mini App API
JWT_SECRET=your_production_jwt_secret_key_minimum_32_characters
JWT_EXPIRE_HOURS=72
ALLOWED_ORIGINS=https://minapp.yourdomain.com,https://t.me
PORT=8000
```

---

## 5. PM2 Process Configuration

The `ecosystem.config.js` in the repository root defines both processes:

```javascript
module.exports = {
  apps: [
    {
      name: "my-python-app",
      script: "./run.sh",
      interpreter: "/bin/bash",
      cwd: "/root/bookbot",
      autorestart: true,
      watch: false,
      max_restarts: 10,
      restart_delay: 3000,
      time: true,
      exp_backoff_restart_delay: 100
    },
    {
      name: "book-api",
      script: "python3",
      args: "-m uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --workers 2",
      cwd: "/root/bookbot",
      autorestart: true,
      watch: false,
      max_restarts: 10,
      restart_delay: 3000,
      time: true,
      exp_backoff_restart_delay: 100,
      env: {
        PORT: 8000,
        PYTHONPATH: "/root/bookbot"
      }
    }
  ]
};
```

### Start / Reload PM2 Services:
```bash
cd /root/bookbot
pm2 start ecosystem.config.js
pm2 save
```

### Useful PM2 Commands:
```bash
# View running status
pm2 status

# Inspect API logs
pm2 logs book-api

# Inspect Bot logs
pm2 logs my-python-app

# Restart API only
pm2 restart book-api
```

---

## 6. Nginx Configuration

Create an Nginx configuration file at `/etc/nginx/sites-available/hbtu-minapp`:

```nginx
server {
    listen 80;
    server_name minapp.yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name minapp.yourdomain.com;

    # SSL Certificate (Certbot)
    ssl_certificate /etc/letsencrypt/live/minapp.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/minapp.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # Static Frontend
    root /root/bookbot/frontend/dist;
    index index.html;

    # Security Headers
    add_header X-Frame-Options "ALLOW-FROM https://web.telegram.org";
    add_header Content-Security-Policy "frame-ancestors 'self' https://web.telegram.org https://*.telegram.org;";
    add_header X-Content-Type-Options "nosniff";

    # Gzip Compression
    gzip on;
    gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss text/javascript;

    # SPA routing - serve index.html for unknown static paths
    location / {
        try_files $uri $uri/ /index.html;
    }

    # Static assets cache
    location /assets/ {
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    # Backend API Proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 60s;
        proxy_connect_timeout 60s;
        client_max_body_size 20M; # Accommodates multi-photo uploads
    }

    # Health Check
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        access_log off;
    }
}
```

Enable and reload Nginx:
```bash
sudo ln -s /etc/nginx/sites-available/hbtu-minapp /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

---

## 7. Telegram BotFather Setup

1. Open Telegram and message [@BotFather](https://t.me/BotFather).
2. Send `/mybots` and choose your bot.
3. Select **Bot Settings** -> **Menu Button** -> **Configure menu button**.
4. Send the Web App URL:
   `https://minapp.yourdomain.com`
5. Send the button title:
   `📚 Open Marketplace`
6. (Optional) Set up inline shortcut or Web App link via BotFather's `/newapp` if you want direct `t.me/bot?startapp=` short links.

---

## 8. Health Verification

Verify deployment endpoints:

```bash
# 1. API Health Check
curl -i https://minapp.yourdomain.com/health
# Expected: {"status":"healthy","service":"hbtu-book-marketplace-api","version":"1.0.0"}

# 2. Frontend HTML
curl -i https://minapp.yourdomain.com/
# Expected: HTTP 200 with <!DOCTYPE html> containing root div

# 3. Process Status
pm2 status
```

---

## 9. Rollback Procedures

If an issue arises after a release:

### Frontend Rollback:
```bash
cd /root/bookbot/frontend
git checkout HEAD~1
npm run build
# Nginx automatically serves the updated dist folder immediately
```

### Backend API Rollback:
```bash
cd /root/bookbot
git checkout HEAD~1 app/api
pm2 restart book-api
```

### Complete Emergency Fallback:
If the Mini App needs to be taken offline temporarily, users can continue using the bot via Telegram chat:
1. In BotFather, disable the Menu Button or point it to a maintenance message.
2. The core bot (`my-python-app`) continues to handle `/start`, `/sell`, and all other chat workflows without interruption.
