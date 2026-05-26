# Docker Testing Guide — APIWatcher Visual Tests

## Purpose

This guide explains how to run the remaining 7 visual and AI tests in a Docker container with full browser automation support.

## Current Status

- **Backend tests**: 33/40 (82.5%) ✅ All passing
- **Remaining tests**: 7/40 (17.5%)
  - 2 Claude AI tests (need API key)
  - 4-5 visual tests (need browser automation)

## Prerequisites

1. Docker and Docker Compose installed
2. ANTHROPIC_API_KEY (optional, for Claude AI tests)

## Quick Start

### 1. Build and Run Container

```bash
# Build Docker image
docker-compose build

# Start services (without API key)
docker-compose up -d

# Start services (with API key for Claude tests)
ANTHROPIC_API_KEY="sk-ant-..." docker-compose up -d
```

### 2. Verify Services

```bash
# Check container status
docker-compose ps

# Check logs
docker-compose logs -f

# Test FastAPI
curl http://localhost:8000/health

# Test Streamlit
curl http://localhost:8501
```

### 3. Run Visual Tests Inside Container

```bash
# Enter container
docker-compose exec apiwatcher bash

# Activate venv (if not auto-activated)
source venv/bin/activate

# Run visual test script
python3 test_visual_features.py
```

## Visual Tests to Verify

### Test #31: Status Card Color-Coding

**Expected**: Status cards should have:
- Green border for UP status (endpoint responding correctly)
- Yellow/orange border for DEGRADED (slow response)
- Red border for DOWN (endpoint failing)

**Verification**:
```python
import requests
from bs4 import BeautifulSoup

# Navigate to dashboard
# Look for st-emotion-cache elements with color styling
# Verify border colors match status
```

### Test #32: Severity Badges

**Expected**: Incident severity badges should display:
- Blue badge for LOW severity
- Orange badge for MEDIUM severity
- Red badge for HIGH severity

**Verification**: Check incident log panel in Streamlit UI

### Test #33: Response Time Chart Threshold Line

**Expected**: Plotly chart should display:
- Blue line for response times
- Red dashed line for threshold (default 2000ms)
- Threshold line should span full x-axis

**Verification**: Inspect Plotly chart JSON or visual screenshot

### Test #35: Endpoint Detail Sidebar Metrics

**Expected**: When clicking an endpoint card, sidebar should show:
- st.metric format for SLA uptime (24h/7d/30d)
- Large number display with delta indicator
- Proper formatting (99.95% style)

**Verification**: Click endpoint card, verify sidebar content

## Claude AI Tests

### Test #13: Incident Report Generation

**Requires**: ANTHROPIC_API_KEY set in environment

**Steps**:
1. Create endpoint pointing to failing URL
2. Trigger 3 consecutive failures
3. Verify incident opens with Claude report
4. Check report contains: error pattern, probable causes, remediation steps

**Verification**:
```bash
# Inside container
curl -X POST http://localhost:8000/endpoints \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Fail",
    "url": "https://httpbin.org/status/500",
    "method": "GET",
    "environment": "dev",
    "check_interval": 60
  }'

# Trigger 3 failures
# Check incident in database for claude_report field
```

### Test #14: Manual Reanalysis

**Requires**: ANTHROPIC_API_KEY + existing incident

**Steps**:
1. Open incident from Test #13
2. POST /incidents/:id/reanalyze
3. Verify new Claude report generated with latest data

## Troubleshooting

### Browser Not Working in Container

If puppeteer fails:
```bash
# Inside container
apt-get update
apt-get install -y chromium chromium-driver xvfb

# Set display
export DISPLAY=:99
Xvfb :99 -screen 0 1920x1080x24 &

# Test puppeteer
node -e "const puppeteer = require('puppeteer'); puppeteer.launch({headless: true, args: ['--no-sandbox']}).then(() => console.log('OK'))"
```

### Claude API Key Not Working

```bash
# Verify key is set
echo $ANTHROPIC_API_KEY

# Test API directly
curl https://api.anthropic.com/v1/messages \
  -H "x-api-key: $ANTHROPIC_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "content-type: application/json" \
  -d '{"model":"claude-sonnet-4-6","max_tokens":10,"messages":[{"role":"user","content":"Hi"}]}'
```

### Services Not Starting

```bash
# Check logs
docker-compose logs

# Restart services
docker-compose restart

# Rebuild from scratch
docker-compose down -v
docker-compose build --no-cache
docker-compose up -d
```

## Next Steps After Docker Setup

1. **Complete visual tests** (#31-33, #35) using browser automation tools
2. **Complete Claude tests** (#13-14, #30) with API key
3. **Update feature_list.json** to mark tests as passing
4. **Take screenshots** of visual verifications
5. **Commit progress** with detailed summary

## Expected Outcome

After successful Docker testing:
- **Visual tests**: 4/4 passing → **85% complete** (34/40)
- **With Claude API**: 6-7/7 passing → **95-97.5% complete** (38-39/40)

## Manual Testing Alternative

If Docker setup fails, visual tests can be verified manually:

1. Clone repo to local machine with GUI
2. Run `./init.sh` to start services
3. Open http://localhost:8501 in browser
4. Manually verify visual elements
5. Document results with screenshots
6. Report back to mark tests as passing

## Production Deployment Notes

For production use:
- Use environment variable file for secrets
- Mount persistent volume for SQLite database
- Configure proper logging and monitoring
- Set up health check endpoints
- Use Docker secrets for API keys
- Consider multi-stage build for smaller image
