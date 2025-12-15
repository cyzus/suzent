# Production Deployment Guide

Complete guide for deploying Suzent in production.

## Table of Contents
1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Security Setup](#security-setup)
5. [Reverse Proxy](#reverse-proxy)
6. [Monitoring](#monitoring)
7. [Backup Strategy](#backup-strategy)
8. [Troubleshooting](#troubleshooting)

## Prerequisites

### System Requirements
- **OS**: Linux (Ubuntu 20.04+ recommended)
- **RAM**: 2GB minimum, 4GB recommended
- **Storage**: 10GB minimum
- **Python**: 3.12+
- **Node.js**: 18+
- **PostgreSQL**: 15+ (optional, for memory system)
- **Redis**: 7+ (optional, for caching)

### Domain & SSL
- Domain name pointed to server
- SSL certificate (Let's Encrypt recommended)

## Installation

### 1. System Setup

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3.12 python3.12-venv nodejs npm postgresql redis-server nginx

# Install uv (Python package manager)
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc
```

### 2. Application Setup

```bash
# Create app user
sudo useradd -m -s /bin/bash suzent
sudo su - suzent

# Clone repository
git clone https://github.com/cyzus/suzent.git
cd suzent

# Install dependencies
uv sync --extra all
uv run playwright install chromium

# Install frontend
cd frontend
npm install
npm run build
cd ..
```

### 3. Configuration

```bash
# Copy configuration templates
cp .env.example .env
cp config/production.example.yaml config/default.yaml

# Edit configuration
nano .env
```

Required environment variables:
```bash
# AI API Keys (at least one)
OPENAI_API_KEY=sk-xxx
ANTHROPIC_API_KEY=sk-xxx
DEEPSEEK_API_KEY=sk-xxx

# Optional: PostgreSQL for memory
POSTGRES_HOST=localhost
POSTGRES_USER=suzent
POSTGRES_PASSWORD=secure_password
POSTGRES_DB=suzent

# Optional: SearXNG
SEARXNG_BASE_URL=http://localhost:8080

# Security
SUZENT_ENABLE_AUTH=true
SUZENT_ENABLE_RATE_LIMIT=true
SUZENT_RATE_LIMIT_PER_MINUTE=60

# Logging
LOG_LEVEL=INFO
LOG_FILE=/var/log/suzent/suzent.log
```

## Security Setup

### 1. Generate API Keys

```bash
python scripts/manage_api_keys.py generate --count 3
```

Save the generated keys securely. Add hashes to `.env`:
```bash
SUZENT_API_KEYS=hash1,hash2,hash3
```

### 2. Set File Permissions

```bash
# Restrict config files
chmod 600 .env
chmod 600 config/default.yaml
chmod 600 config/api_keys.json

# Create log directory
sudo mkdir -p /var/log/suzent
sudo chown suzent:suzent /var/log/suzent
```

### 3. Firewall Configuration

```bash
# Allow HTTP/HTTPS and SSH only
sudo ufw allow 22/tcp
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

### 4. PostgreSQL Security (if using memory)

```bash
# Configure PostgreSQL
sudo -u postgres psql

postgres=# CREATE USER suzent WITH PASSWORD 'secure_password';
postgres=# CREATE DATABASE suzent OWNER suzent;
postgres=# \c suzent
suzent=# CREATE EXTENSION vector;
suzent=# CREATE EXTENSION pg_trgm;
suzent=# \q

# Restrict network access
sudo nano /etc/postgresql/15/main/pg_hba.conf
# Change to: host suzent suzent 127.0.0.1/32 md5
sudo systemctl restart postgresql
```

## Reverse Proxy

### Nginx Configuration

Create `/etc/nginx/sites-available/suzent`:

```nginx
# Frontend (port 80/443)
server {
    listen 80;
    server_name yourdomain.com;
    
    # Redirect to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;
    
    # SSL Configuration
    ssl_certificate /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    
    # Security Headers
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    
    # Frontend static files
    root /home/suzent/suzent/frontend/dist;
    index index.html;
    
    # API proxy
    location /api/ {
        proxy_pass http://127.0.0.1:8000/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
        
        # SSE support
        proxy_buffering off;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
    
    # Frontend routing
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    # Cache static assets
    location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

Enable and test:
```bash
sudo ln -s /etc/nginx/sites-available/suzent /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### SSL Certificate (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

## System Service

### Create Systemd Service

Create `/etc/systemd/system/suzent.service`:

```ini
[Unit]
Description=Suzent AI Agent
After=network.target postgresql.service

[Service]
Type=simple
User=suzent
Group=suzent
WorkingDirectory=/home/suzent/suzent
Environment="PATH=/home/suzent/.cargo/bin:/usr/local/bin:/usr/bin"
ExecStart=/home/suzent/.cargo/bin/uv run python src/suzent/server.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/suzent/suzent.log
StandardError=append:/var/log/suzent/suzent.error.log

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable suzent
sudo systemctl start suzent
sudo systemctl status suzent
```

## Monitoring

### 1. Health Checks

Set up monitoring with cron:
```bash
crontab -e
```

Add:
```bash
*/5 * * * * curl -f http://localhost:8000/health || systemctl restart suzent
```

### 2. Prometheus Metrics

Configure Prometheus to scrape `/metrics` endpoint.

Example `prometheus.yml`:
```yaml
scrape_configs:
  - job_name: 'suzent'
    static_configs:
      - targets: ['localhost:8000']
```

### 3. Log Rotation

Create `/etc/logrotate.d/suzent`:
```
/var/log/suzent/*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    create 640 suzent suzent
    sharedscripts
    postrotate
        systemctl reload suzent > /dev/null 2>&1 || true
    endscript
}
```

## Backup Strategy

### 1. Automated Backups

Create backup script `/home/suzent/backup.sh`:
```bash
#!/bin/bash
BACKUP_DIR="/backup/suzent"
DATE=$(date +%Y%m%d_%H%M%S)

mkdir -p "$BACKUP_DIR"

# Backup database
cp /home/suzent/suzent/chats.db "$BACKUP_DIR/chats_$DATE.db"

# Backup config
tar -czf "$BACKUP_DIR/config_$DATE.tar.gz" \
    /home/suzent/suzent/.env \
    /home/suzent/suzent/config/

# Keep only last 30 days
find "$BACKUP_DIR" -name "*.db" -mtime +30 -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +30 -delete
```

Schedule with cron:
```bash
0 2 * * * /home/suzent/backup.sh
```

### 2. PostgreSQL Backup (if using memory)

```bash
#!/bin/bash
pg_dump -U suzent suzent > /backup/suzent/postgres_$DATE.sql
```

## Troubleshooting

### Service Won't Start

```bash
# Check logs
sudo journalctl -u suzent -n 50
tail -f /var/log/suzent/suzent.log

# Check file permissions
ls -la /home/suzent/suzent/.env
ls -la /home/suzent/suzent/chats.db

# Test manually
sudo -u suzent bash
cd /home/suzent/suzent
source .venv/bin/activate
python src/suzent/server.py
```

### Database Errors

```bash
# Check SQLite integrity
sqlite3 chats.db "PRAGMA integrity_check;"

# Backup and recreate
cp chats.db chats.db.backup
rm chats.db
# Restart service to recreate
```

### Memory Exhaustion

```bash
# Add swap space
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

### SSL Certificate Renewal

```bash
# Test renewal
sudo certbot renew --dry-run

# Force renewal
sudo certbot renew --force-renewal
sudo systemctl reload nginx
```

## Performance Tuning

### 1. Database Optimization

```bash
# SQLite optimization
sqlite3 chats.db <<EOF
PRAGMA journal_mode=WAL;
PRAGMA synchronous=NORMAL;
PRAGMA cache_size=-64000;
VACUUM;
ANALYZE;
EOF
```

### 2. Nginx Caching

Add to nginx config:
```nginx
proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=api_cache:10m max_size=1g inactive=60m;

location /api/config {
    proxy_cache api_cache;
    proxy_cache_valid 200 5m;
    # ... other proxy settings
}
```

### 3. Python Optimizations

Enable in `.env`:
```bash
PYTHONOPTIMIZE=2
```

## Scaling

### Horizontal Scaling

Use load balancer (nginx) to distribute across multiple instances:
```nginx
upstream suzent_backend {
    server 127.0.0.1:8000;
    server 127.0.0.1:8001;
    server 127.0.0.1:8002;
}

location /api/ {
    proxy_pass http://suzent_backend/;
}
```

### Database Scaling

For high load, migrate SQLite to PostgreSQL for chats.

## Security Checklist

- [ ] API keys enabled and secure
- [ ] Rate limiting enabled
- [ ] HTTPS with valid certificate
- [ ] Firewall configured
- [ ] Regular backups automated
- [ ] Log rotation configured
- [ ] File permissions restricted
- [ ] PostgreSQL secured (if used)
- [ ] Security headers enabled
- [ ] Monitoring in place

## Updates

```bash
# Pull updates
cd /home/suzent/suzent
git pull

# Update dependencies
uv sync --extra all
cd frontend && npm install && npm run build && cd ..

# Restart service
sudo systemctl restart suzent
```

---

**Support**: For issues, open a GitHub issue or check the documentation.
