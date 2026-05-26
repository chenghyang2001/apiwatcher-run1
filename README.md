# APIWatcher — REST API Endpoint Monitor

APIWatcher is a lightweight web-based monitoring tool that continuously checks REST API endpoints for availability, correctness, and performance. It uses FastAPI for the backend service, Streamlit for the dashboard, and Claude AI for intelligent incident analysis.

## Features

- **Endpoint Health Monitoring**: Continuous checks with configurable intervals (60s to 86400s)
- **Incident Detection**: Auto-open incidents after 3 consecutive failures, auto-close after 2 passing checks
- **Claude AI Reports**: Intelligent incident analysis with root cause suggestions
- **Multi-Channel Alerts**: Email, Slack webhooks, and desktop notifications
- **SLA Tracking**: Calculate uptime % over 24h/7d/30d rolling windows
- **Response Time Trends**: Real-time Plotly charts with threshold overlays
- **Multi-Environment Support**: Separate dev/staging/production endpoint groups
- **YAML Import/Export**: Easy endpoint configuration management

## Technology Stack

- **Backend**: Python 3.11+, FastAPI, APScheduler, httpx, SQLAlchemy
- **Frontend**: Streamlit, Plotly Express
- **Database**: SQLite
- **AI**: Anthropic Claude API (claude-sonnet-4-6)
- **Alerts**: smtplib (email), httpx (Slack), plyer (desktop)

## Prerequisites

- Python 3.11 or higher
- ANTHROPIC_API_KEY environment variable (for Claude AI incident reports)
- Ports 8000 (FastAPI) and 8501 (Streamlit) available

## Quick Start

1. **Set up the environment**:
   ```bash
   ./init.sh
   ```

2. **Set your Anthropic API key**:
   ```bash
   export ANTHROPIC_API_KEY="sk-ant-..."
   # Or use the test key at /tmp/api-key
   ```

3. **Access the application**:
   - Streamlit Dashboard: http://localhost:8501
   - FastAPI Service: http://localhost:8000
   - API Documentation: http://localhost:8000/docs

## Project Structure

```
watcher/
  __init__.py           # Package initialization
  models.py             # SQLAlchemy ORM models (Endpoint, Check, Incident, AlertConfig)
  db.py                 # SQLite engine and session factory
  checker.py            # Async HTTP health check execution
  scheduler.py          # APScheduler job management
  incident.py           # Incident detection logic (3-fail open, 2-pass close)
  alerter.py            # Multi-channel alert sender (email, Slack, desktop)
  claude_reporter.py    # Claude AI incident report generation
  api.py                # FastAPI REST API application
  dashboard.py          # Streamlit dashboard UI
  sla.py                # SLA uptime calculation and CSV export
```

## API Endpoints

### Endpoints Management
- `GET /endpoints` - List all endpoints
- `POST /endpoints` - Create new endpoint
- `GET /endpoints/:id` - Get endpoint details
- `PUT /endpoints/:id` - Update endpoint
- `DELETE /endpoints/:id` - Delete endpoint
- `POST /endpoints/:id/check` - Trigger manual check
- `PUT /endpoints/:id/toggle` - Enable/disable endpoint
- `GET /endpoints/export` - Export as YAML
- `POST /endpoints/import` - Import from YAML

### Monitoring
- `GET /checks/:endpoint_id` - Get check history
- `GET /checks/:endpoint_id/latest` - Get latest check

### Incidents
- `GET /incidents` - List all incidents
- `GET /incidents/:id` - Get incident details with Claude report
- `PUT /incidents/:id/acknowledge` - Mark as acknowledged
- `POST /incidents/:id/reanalyze` - Regenerate Claude AI analysis

### SLA
- `GET /sla/:endpoint_id` - Get uptime metrics (24h/7d/30d)
- `GET /sla/:endpoint_id/export` - Export SLA history as CSV

### Alerts
- `GET /alerts` - Get alert send log
- `GET /alert-configs/:endpoint_id` - Get alert configuration
- `PUT /alert-configs/:endpoint_id` - Update alert settings

### Health
- `GET /health` - Service health check

## Development

### Manual Setup

If you prefer not to use `init.sh`:

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start FastAPI
uvicorn watcher.api:app --port 8000 --reload

# Start Streamlit (in another terminal)
streamlit run watcher/dashboard.py --server.port 8501
```

### Running Tests

```bash
pytest
```

## Database Schema

### endpoints
- Stores monitored API endpoint configurations
- Fields: name, url, method, headers, body, environment, check_interval, timeout_ms, expected_status, sla_target, enabled

### checks
- Stores individual health check results
- Fields: endpoint_id, checked_at, passed, status_code, response_time, error_message, response_body

### incidents
- Tracks endpoint failure incidents
- Fields: endpoint_id, started_at, resolved_at, duration_mins, failure_count, severity, claude_report, acknowledged

### alert_configs
- Per-endpoint alert channel configurations
- Fields: endpoint_id, channel, target, on_incident, on_resolve, on_sla_breach, cooldown_mins, last_sent_at

## Configuration

### Endpoint Configuration
Each endpoint can specify:
- **Check interval**: 60-86400 seconds (default: 300)
- **Timeout**: milliseconds (default: 5000)
- **Expected status**: HTTP status code (default: 200)
- **Keyword check**: Optional keyword that must appear in response body
- **SLA target**: Uptime percentage threshold (default: 99.9%)
- **Environment**: dev, staging, or production

### Alert Configuration
Per endpoint, per channel:
- **Email**: SMTP with TLS support
- **Slack**: Webhook URL
- **Desktop**: Local plyer notifications
- **Cooldown**: Minimum 15 minutes between repeat alerts

## Architecture

```
┌─────────────────┐         ┌──────────────┐
│   Streamlit     │◄───────►│   SQLite     │
│  Dashboard      │         │   Database   │
│  (port 8501)    │         │              │
└─────────────────┘         └──────▲───────┘
                                   │
                                   │
┌─────────────────┐                │
│    FastAPI      │◄───────────────┘
│    Service      │
│  (port 8000)    │
└────────┬────────┘
         │
         ├──► APScheduler (background checks)
         ├──► httpx (HTTP client)
         ├──► Anthropic Claude API (incident reports)
         └──► Alerter (email, Slack, desktop)
```

## License

MIT

## Author

Generated by autonomous Claude Code agent
