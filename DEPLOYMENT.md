# Production Deployment Guide 🚀

Panduan lengkap untuk deploy URL Shortener API ke production.

## Prerequisites

- Ubuntu/Debian server (or any Linux)
- Python 3.9+
- PostgreSQL 13+ (recommended) atau MySQL
- Nginx (reverse proxy)
- Domain name (optional tapi recommended)
- SSL certificate (Let's Encrypt)

## Deployment Options

### Option 1: Docker Compose (Recommended)

Paling mudah dan cepat!

#### Step 1: Install Docker

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.23.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

#### Step 2: Setup Project

```bash
# Clone repository
git clone <your-repo>
cd url-shortener

# Create .env file
cp .env.example .env
nano .env
```

Edit `.env`:
```env
SUPER_ADMIN_KEY=generate-a-very-secure-random-string-here
BASE_URL=https://short.yourdomain.com
CORS_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
```

#### Step 3: Deploy

```bash
# Build and start
docker-compose up -d

# Check logs
docker-compose logs -f

# Check status
docker-compose ps
```

#### Step 4: Setup Nginx Reverse Proxy

```bash
sudo nano /etc/nginx/sites-available/urlshortener
```

```nginx
server {
    listen 80;
    server_name short.yourdomain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```bash
# Enable site
sudo ln -s /etc/nginx/sites-available/urlshortener /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx

# Setup SSL with Let's Encrypt
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d short.yourdomain.com
```

### Option 2: Manual Deployment with systemd

#### Step 1: Setup Python Environment

```bash
# Install system dependencies
sudo apt update
sudo apt install python3.11 python3.11-venv python3-pip postgresql nginx

# Create application user
sudo useradd -m -s /bin/bash urlshortener
sudo su - urlshortener

# Setup project
git clone <your-repo>
cd url-shortener
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

#### Step 2: Setup PostgreSQL

```bash
# Switch to postgres user
sudo -u postgres psql

# In PostgreSQL:
CREATE DATABASE urlshortener;
CREATE USER urlshortener WITH PASSWORD 'secure-password';
GRANT ALL PRIVILEGES ON DATABASE urlshortener TO urlshortener;
\q
```

#### Step 3: Configure Environment

```bash
nano .env
```

```env
SUPER_ADMIN_KEY=your-super-secure-key
BASE_URL=https://short.yourdomain.com
DATABASE_URL=postgresql://urlshortener:secure-password@localhost/urlshortener
CORS_ORIGINS=https://yourdomain.com
```

#### Step 4: Create systemd Service

```bash
sudo nano /etc/systemd/system/urlshortener.service
```

```ini
[Unit]
Description=URL Shortener API
After=network.target postgresql.service

[Service]
Type=notify
User=urlshortener
Group=urlshortener
WorkingDirectory=/home/urlshortener/url-shortener
Environment="PATH=/home/urlshortener/url-shortener/venv/bin"
EnvironmentFile=/home/urlshortener/url-shortener/.env
ExecStart=/home/urlshortener/url-shortener/venv/bin/gunicorn main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000 \
    --access-logfile /var/log/urlshortener/access.log \
    --error-logfile /var/log/urlshortener/error.log \
    --log-level info
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Create log directory
sudo mkdir -p /var/log/urlshortener
sudo chown urlshortener:urlshortener /var/log/urlshortener

# Start service
sudo systemctl daemon-reload
sudo systemctl enable urlshortener
sudo systemctl start urlshortener
sudo systemctl status urlshortener
```

#### Step 5: Setup Nginx (same as Docker option above)

### Option 3: Deploy to Cloud Platforms

#### Deploy to DigitalOcean App Platform

1. Push code ke GitHub
2. Di DigitalOcean App Platform, create new app
3. Connect GitHub repo
4. Set environment variables
5. Deploy!

**App Spec:**
```yaml
name: url-shortener
services:
  - name: api
    github:
      repo: your-username/url-shortener
      branch: main
    build_command: pip install -r requirements.txt
    run_command: uvicorn main:app --host 0.0.0.0 --port 8080
    envs:
      - key: SUPER_ADMIN_KEY
        value: your-secure-key
      - key: BASE_URL
        value: ${APP_URL}
      - key: DATABASE_URL
        value: ${db.DATABASE_URL}
    http_port: 8080
databases:
  - name: db
    engine: PG
    version: "15"
```

#### Deploy to Railway

```bash
# Install Railway CLI
npm i -g @railway/cli

# Login
railway login

# Initialize
railway init

# Add PostgreSQL
railway add

# Set environment variables
railway variables set SUPER_ADMIN_KEY=your-key
railway variables set BASE_URL=https://your-app.up.railway.app

# Deploy
railway up
```

#### Deploy to Heroku

```bash
# Install Heroku CLI
# https://devcenter.heroku.com/articles/heroku-cli

# Login
heroku login

# Create app
heroku create your-url-shortener

# Add PostgreSQL
heroku addons:create heroku-postgresql:mini

# Set environment variables
heroku config:set SUPER_ADMIN_KEY=your-secure-key
heroku config:set BASE_URL=https://your-url-shortener.herokuapp.com

# Create Procfile
echo "web: uvicorn main:app --host 0.0.0.0 --port \$PORT" > Procfile

# Deploy
git push heroku main
```

## Post-Deployment Checklist

### Security

- [ ] HTTPS enabled (SSL certificate)
- [ ] SUPER_ADMIN_KEY is strong and secure
- [ ] Database credentials secure
- [ ] CORS properly configured
- [ ] Firewall configured (allow only 80, 443)
- [ ] Regular security updates scheduled

### Monitoring

- [ ] Setup health check monitoring (UptimeRobot, Pingdom)
- [ ] Configure log rotation
- [ ] Setup error tracking (Sentry)
- [ ] Monitor database size
- [ ] Setup backup automation

### Performance

- [ ] Enable gzip compression in Nginx
- [ ] Configure caching headers
- [ ] Setup CDN for static files (QR codes)
- [ ] Database connection pooling configured
- [ ] Indexes properly set

### Backup Strategy

```bash
# Create backup script
cat > /home/urlshortener/backup.sh << 'EOF'
#!/bin/bash
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR=/home/urlshortener/backups
mkdir -p $BACKUP_DIR

# Backup database
pg_dump -U urlshortener urlshortener > $BACKUP_DIR/db_$DATE.sql

# Compress
gzip $BACKUP_DIR/db_$DATE.sql

# Keep only last 30 days
find $BACKUP_DIR -name "db_*.sql.gz" -mtime +30 -delete

# Upload to S3 (optional)
# aws s3 cp $BACKUP_DIR/db_$DATE.sql.gz s3://your-bucket/backups/
EOF

chmod +x /home/urlshortener/backup.sh

# Add to crontab (daily at 2 AM)
crontab -e
# Add: 0 2 * * * /home/urlshortener/backup.sh
```

## Monitoring Setup

### Setup Prometheus + Grafana (Optional)

```yaml
# docker-compose.monitoring.yml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
```

### Setup Log Monitoring

```bash
# Install Loki for log aggregation
# https://grafana.com/docs/loki/latest/setup/install/docker/
```

## Performance Tuning

### Nginx Configuration

```nginx
# /etc/nginx/nginx.conf
http {
    # Gzip compression
    gzip on;
    gzip_vary on;
    gzip_proxied any;
    gzip_comp_level 6;
    gzip_types text/plain text/css application/json application/javascript;

    # Connection limits
    limit_conn_zone $binary_remote_addr zone=addr:10m;
    limit_req_zone $binary_remote_addr zone=req_limit_per_ip:10m rate=10r/s;

    # Cache
    proxy_cache_path /var/cache/nginx levels=1:2 keys_zone=my_cache:10m max_size=1g inactive=60m;
}

server {
    # Rate limiting
    limit_req zone=req_limit_per_ip burst=20 nodelay;
    limit_conn addr 10;

    # Caching for QR codes
    location /qr/ {
        proxy_pass http://localhost:8000;
        proxy_cache my_cache;
        proxy_cache_valid 200 1d;
        add_header X-Cache-Status $upstream_cache_status;
    }
}
```

### Database Optimization

```sql
-- Create indexes for better performance
CREATE INDEX idx_urls_created_at ON urls(created_at DESC);
CREATE INDEX idx_url_clicks_url_id_time ON url_clicks(url_id, clicked_at DESC);
CREATE INDEX idx_api_keys_key_active ON api_keys(key, is_active);

-- Enable query optimization
ANALYZE urls;
ANALYZE url_clicks;
ANALYZE api_keys;
```

### Application Tuning

```python
# In main.py, adjust workers based on CPU cores
# workers = (2 × CPU cores) + 1

# For 4 core server:
# gunicorn ... --workers 9
```

## Scaling Strategies

### Horizontal Scaling

```
Load Balancer (nginx)
    ├── API Server 1
    ├── API Server 2
    ├── API Server 3
    └── API Server 4
          ↓
    Database (PostgreSQL with replication)
          ↓
    Redis Cache (optional)
```

### Vertical Scaling

- Upgrade server resources (CPU, RAM)
- Optimize database (more RAM, faster SSD)
- Add read replicas for database

## Troubleshooting

### Check Logs

```bash
# Application logs
sudo journalctl -u urlshortener -f

# Nginx logs
sudo tail -f /var/log/nginx/error.log
sudo tail -f /var/log/nginx/access.log

# Docker logs
docker-compose logs -f api
```

### Common Issues

**Issue**: 502 Bad Gateway
```bash
# Check if app is running
sudo systemctl status urlshortener
# Check if port is listening
sudo netstat -tulpn | grep 8000
```

**Issue**: High memory usage
```bash
# Check memory
free -h
# Restart service
sudo systemctl restart urlshortener
```

**Issue**: Slow database queries
```sql
-- Check slow queries
SELECT * FROM pg_stat_statements 
ORDER BY mean_exec_time DESC 
LIMIT 10;
```

## Maintenance

### Regular Tasks

**Daily:**
- Monitor error logs
- Check service status
- Review analytics

**Weekly:**
- Review backup status
- Check disk space
- Update dependencies if needed

**Monthly:**
- Security updates
- Database optimization (VACUUM)
- Review and clean old URLs

### Update Procedure

```bash
# Backup first!
./backup.sh

# Pull latest code
git pull origin main

# Update dependencies
source venv/bin/activate
pip install -r requirements.txt --upgrade

# Restart service
sudo systemctl restart urlshortener

# Verify
curl https://short.yourdomain.com/health
```

## Support & Resources

- Documentation: `/docs` endpoint
- Health Check: `/health` endpoint
- Metrics: Setup Prometheus metrics
- Logs: Centralized logging with Loki/ELK

---

**Ready for Production! 🎉**
