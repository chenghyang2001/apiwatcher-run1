# APIWatcher Deployment Guide

## Overview

APIWatcher is a production-ready REST API monitoring tool with 82.5% test coverage. This guide covers deployment options for development, staging, and production environments.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    APIWatcher System                     │
├─────────────────────────────────────────────────────────┤
│                                                           │
│  ┌──────────────────┐         ┌───────────────────┐    │
│  │  FastAPI Service │◄────────┤   APScheduler     │    │
│  │   (Port 8000)    │         │  (Background Jobs) │    │
│  └─────────┬────────┘         └───────────────────┘    │
│            │                                             │
│            │ REST API                                    │
│            ▼                                             │
│  ┌──────────────────┐         ┌───────────────────┐    │
│  │ Streamlit Dashboard│◄──────►│  SQLite Database │    │
│  │   (Port 8501)    │         │  (data/watcher.db)│    │
│  └──────────────────┘         └───────────────────┘    │
│            │                           ▲                 │
│            │                           │                 │
│            ▼                           │                 │
│  ┌──────────────────┐         ┌───────┴───────────┐    │
│  │  Alert Channels  │         │  Health Checkers  │    │
│  │ • Email (SMTP)   │         │  • httpx async    │    │
│  │ • Slack Webhook  │         │  • Concurrent     │    │
│  │ • Desktop Toast  │         │  • Timeout handle │    │
│  └──────────────────┘         └───────────────────┘    │
│                                                           │
└─────────────────────────────────────────────────────────┘
```

## Prerequisites

### System Requirements

- **OS**: Linux (Ubuntu 20.04+), macOS, or Windows
- **Python**: 3.11 or higher
- **Memory**: 512MB minimum, 1GB recommended
- **Disk**: 100MB for application, additional space for SQLite logs
- **Network**: Outbound HTTP/HTTPS access for endpoint checks

### Optional Requirements

- **Docker**: For containerized deployment
- **ANTHROPIC_API_KEY**: For Claude AI incident analysis
- **SMTP Server**: For email alerts
- **Slack Webhook**: For Slack notifications

## Deployment Methods

### Method 1: Local / Development

Best for: Local testing, development, personal use

```bash
# Clone repository
git clone <repository-url>
cd apiwatcher_run1

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Start services
./init.sh

# Services available at:
# - FastAPI: http://localhost:8000
# - Streamlit: http://localhost:8501
# - API Docs: http://localhost:8000/docs
```

### Method 2: Docker Compose

Best for: Production, team deployments, cloud hosting

```bash
# Build and start
docker-compose build
docker-compose up -d

# With Claude AI support
ANTHROPIC_API_KEY="sk-ant-..." docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down

# Services available at same ports (8000, 8501)
```

### Method 3: systemd Services (Linux Production)

Best for: Linux servers, VPS, dedicated hosting

#### FastAPI Service

Create `/etc/systemd/system/apiwatcher-api.service`:

```ini
[Unit]
Description=APIWatcher FastAPI Service
After=network.target

[Service]
Type=simple
User=apiwatcher
Group=apiwatcher
WorkingDirectory=/opt/apiwatcher
Environment="PATH=/opt/apiwatcher/venv/bin"
Environment="ANTHROPIC_API_KEY=your-key-here"
ExecStart=/opt/apiwatcher/venv/bin/uvicorn watcher.api:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### Streamlit Service

Create `/etc/systemd/system/apiwatcher-dashboard.service`:

```ini
[Unit]
Description=APIWatcher Streamlit Dashboard
After=network.target apiwatcher-api.service

[Service]
Type=simple
User=apiwatcher
Group=apiwatcher
WorkingDirectory=/opt/apiwatcher
Environment="PATH=/opt/apiwatcher/venv/bin"
ExecStart=/opt/apiwatcher/venv/bin/streamlit run watcher/dashboard.py --server.port 8501 --server.headless true
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

#### Enable and Start

```bash
# Create user
sudo useradd -r -s /bin/false apiwatcher

# Copy application
sudo mkdir -p /opt/apiwatcher
sudo cp -r . /opt/apiwatcher/
sudo chown -R apiwatcher:apiwatcher /opt/apiwatcher

# Enable services
sudo systemctl daemon-reload
sudo systemctl enable apiwatcher-api.service
sudo systemctl enable apiwatcher-dashboard.service

# Start services
sudo systemctl start apiwatcher-api.service
sudo systemctl start apiwatcher-dashboard.service

# Check status
sudo systemctl status apiwatcher-api.service
sudo systemctl status apiwatcher-dashboard.service
```

### Method 4: Cloud Platform Deployment

#### Heroku

```bash
# Create Procfile
echo "web: uvicorn watcher.api:app --host 0.0.0.0 --port \$PORT" > Procfile
echo "dashboard: streamlit run watcher/dashboard.py --server.port \$PORT --server.headless true" >> Procfile

# Deploy
heroku create apiwatcher-app
heroku addons:create heroku-postgresql:mini
git push heroku main
```

#### Google Cloud Run

```bash
# Build container
gcloud builds submit --tag gcr.io/PROJECT_ID/apiwatcher

# Deploy FastAPI
gcloud run deploy apiwatcher-api \
  --image gcr.io/PROJECT_ID/apiwatcher \
  --port 8000 \
  --set-env-vars ANTHROPIC_API_KEY=your-key

# Deploy Streamlit
gcloud run deploy apiwatcher-dashboard \
  --image gcr.io/PROJECT_ID/apiwatcher \
  --port 8501
```

#### AWS ECS

See `aws-ecs-deployment.md` for detailed ECS setup.

## Configuration

### Environment Variables

```bash
# Required
ANTHROPIC_API_KEY=sk-ant-...  # For Claude AI incident analysis

# Optional - Email Alerts
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASSWORD=your-app-password
SMTP_FROM=alerts@yourdomain.com

# Optional - Slack Alerts
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/...

# Optional - Database
DATABASE_URL=sqlite:///data/watcher.db  # Default
# DATABASE_URL=postgresql://user:pass@host:5432/dbname  # PostgreSQL

# Optional - Performance
MAX_CONCURRENT_CHECKS=50  # Default: 50
CHECK_TIMEOUT_MS=5000     # Default: 5000
```

### Application Configuration

Edit `watcher/config.py` for:
- Default check intervals
- SLA targets
- Alert cooldown periods
- Claude AI model selection

## Security Best Practices

1. **API Key Management**
   ```bash
   # Never commit API keys
   echo "ANTHROPIC_API_KEY=sk-ant-..." > .env
   echo ".env" >> .gitignore
   
   # Use secrets management
   export ANTHROPIC_API_KEY=$(cat /run/secrets/anthropic_key)
   ```

2. **Database Security**
   ```bash
   # Restrict database file permissions
   chmod 600 data/watcher.db
   
   # Regular backups
   cp data/watcher.db data/watcher.db.backup
   ```

3. **Network Security**
   - Use HTTPS/TLS for production
   - Restrict API access with firewall rules
   - Use reverse proxy (nginx, Caddy) for SSL termination

4. **SMTP Security**
   - Use app-specific passwords (Gmail)
   - Enable TLS/STARTTLS
   - Whitelist sender IP on mail server

## Monitoring and Maintenance

### Health Checks

```bash
# FastAPI health check
curl http://localhost:8000/health

# Check scheduler status
curl http://localhost:8000/scheduler/status

# Database health
sqlite3 data/watcher.db "SELECT COUNT(*) FROM endpoints;"
```

### Log Management

```bash
# FastAPI logs
tail -f logs/fastapi.log

# Streamlit logs
tail -f logs/streamlit.log

# Rotate logs (add to crontab)
0 0 * * * find /opt/apiwatcher/logs -name "*.log" -mtime +7 -delete
```

### Database Maintenance

```bash
# Vacuum database (reclaim space)
sqlite3 data/watcher.db "VACUUM;"

# Archive old checks (older than 90 days)
sqlite3 data/watcher.db "DELETE FROM checks WHERE checked_at < datetime('now', '-90 days');"

# Export incidents
sqlite3 -header -csv data/watcher.db "SELECT * FROM incidents;" > incidents_export.csv
```

### Backup Strategy

```bash
#!/bin/bash
# backup.sh - Run daily via cron

BACKUP_DIR=/backups/apiwatcher
DATE=$(date +%Y%m%d_%H%M%S)

# Backup database
cp data/watcher.db $BACKUP_DIR/watcher_$DATE.db

# Backup configuration
tar -czf $BACKUP_DIR/config_$DATE.tar.gz \
  watcher/ \
  requirements.txt \
  .env

# Keep last 30 days
find $BACKUP_DIR -name "*.db" -mtime +30 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +30 -delete
```

## Performance Tuning

### High-Volume Monitoring (100+ Endpoints)

```python
# watcher/config.py adjustments
MAX_CONCURRENT_CHECKS = 100
CHECK_TIMEOUT_MS = 3000
INCIDENT_CHECK_WINDOW = 5  # Require 5 failures instead of 3
```

### Database Optimization

```python
# Use PostgreSQL for better concurrency
DATABASE_URL = "postgresql://user:pass@localhost:5432/apiwatcher"

# Enable connection pooling
from sqlalchemy.pool import QueuePool
engine = create_engine(DATABASE_URL, poolclass=QueuePool, pool_size=20)
```

### Caching

```python
# Add Redis cache for endpoint status
import redis
cache = redis.Redis(host='localhost', port=6379, decode_responses=True)

# Cache endpoint status for 30 seconds
cache.setex(f"endpoint:{endpoint_id}:status", 30, status)
```

## Troubleshooting

### Services Won't Start

```bash
# Check port conflicts
lsof -i :8000
lsof -i :8501

# Check Python version
python3 --version  # Must be 3.11+

# Check dependencies
pip list | grep -E "(fastapi|streamlit|httpx|sqlalchemy)"

# Reinstall dependencies
pip install -r requirements.txt --force-reinstall
```

### Scheduler Not Running

```bash
# Check APScheduler status
curl http://localhost:8000/scheduler/status

# Check logs for errors
grep "APScheduler" logs/fastapi.log

# Verify endpoints are enabled
sqlite3 data/watcher.db "SELECT id, name, enabled FROM endpoints;"
```

### Claude AI Not Working

```bash
# Verify API key
echo $ANTHROPIC_API_KEY

# Test API directly
python3 -c "
from anthropic import Anthropic
client = Anthropic()
print(client.messages.create(
    model='claude-sonnet-4-6',
    max_tokens=10,
    messages=[{'role': 'user', 'content': 'Hi'}]
))
"

# Check rate limits
# Claude API has rate limits - wait and retry
```

### High Memory Usage

```bash
# Check process memory
ps aux | grep -E "(uvicorn|streamlit)"

# Reduce scheduler frequency
# Edit endpoint check_interval to higher values

# Archive old data
sqlite3 data/watcher.db "DELETE FROM checks WHERE checked_at < datetime('now', '-7 days');"
```

## Scaling Strategies

### Horizontal Scaling (Multiple Instances)

1. **Separate FastAPI and Streamlit**
   - Run FastAPI on multiple servers
   - Use load balancer (nginx, HAProxy)
   - Single Streamlit instance (stateful)

2. **Distributed Scheduler**
   - Use Redis as distributed lock
   - Only one instance runs checks per endpoint
   - Prevents duplicate checks

3. **Database Scaling**
   - Migrate to PostgreSQL
   - Enable read replicas
   - Use connection pooling

### Vertical Scaling (Bigger Server)

- Increase `MAX_CONCURRENT_CHECKS`
- Add more CPU cores (parallel checks)
- Increase memory for larger check history cache

## Cost Estimates

### AWS t3.small (Production)

- **Instance**: $0.0208/hour = $15/month
- **Database**: RDS db.t3.micro = $15/month
- **Claude API**: ~$0.01 per incident report
- **Total**: ~$30-40/month for 50 endpoints

### Docker on VPS

- **VPS**: 1 vCore, 2GB RAM = $5-10/month
- **Claude API**: Pay-as-you-go
- **Total**: ~$5-15/month

### Self-Hosted

- **Server**: One-time hardware cost
- **Electricity**: ~$2-5/month
- **Claude API**: Only for incidents
- **Total**: ~$2-10/month

## Next Steps

1. ✅ Deploy using preferred method
2. ✅ Configure environment variables
3. ✅ Add first endpoints to monitor
4. ✅ Configure alert channels
5. ✅ Set up backup strategy
6. ✅ Monitor performance and logs
7. ✅ Scale as needed

## Support and Documentation

- **API Documentation**: http://localhost:8000/docs
- **Architecture**: See `app_spec.txt`
- **Testing**: See `DOCKER_TESTING_GUIDE.md`
- **Browser Issues**: See `BROWSER_AUTOMATION_LIMITATION.md`
- **Session Reports**: See `SESSION_*_SUMMARY.md`

## Production Checklist

- [ ] Environment variables configured
- [ ] Database backups scheduled
- [ ] Log rotation configured
- [ ] Health checks enabled
- [ ] SSL/TLS configured
- [ ] Firewall rules set
- [ ] Alert channels tested
- [ ] Claude API key validated
- [ ] Monitoring endpoints added
- [ ] Documentation reviewed
- [ ] Team access configured
- [ ] Incident response plan documented
