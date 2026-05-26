# Streamlit UI Testing Guide

## Environment Requirements

To test the remaining 12 Streamlit UI features, you need an environment with:

1. **Browser Automation Support**
   - Puppeteer/Chrome with working sandbox OR --no-sandbox flag enabled
   - Not blocked by AppArmor on Ubuntu 23.10+
   - Alternative: Run on Ubuntu 22.04 or another Linux distro without strict AppArmor

2. **Claude API Access** (for features #13-14)
   - Set `ANTHROPIC_API_KEY` environment variable
   - OR place API key in `/tmp/api-key` file

## Remaining Tests (14 total)

### Claude AI Features (2 tests)

#### Feature #13: Claude AI Incident Report Generation
**Requires:** ANTHROPIC_API_KEY

```bash
# Set API key
export ANTHROPIC_API_KEY="sk-ant-..."

# Test steps:
# 1. Create endpoint pointing to failing URL
curl -X POST http://localhost:8000/endpoints \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Failing Endpoint",
    "url": "https://httpbin.org/status/503",
    "method": "GET",
    "environment": "dev",
    "check_interval": 300,
    "enabled": true
  }'

# 2. Trigger 3 consecutive failures (replace :id with actual endpoint ID)
curl -X POST http://localhost:8000/endpoints/:id/check
curl -X POST http://localhost:8000/endpoints/:id/check
curl -X POST http://localhost:8000/endpoints/:id/check

# 3. Wait 10-15 seconds for Claude report generation
sleep 15

# 4. Check incident record for claude_report field
curl http://localhost:8000/incidents | python3 -m json.tool

# Expected: Latest incident should have claude_report populated with AI analysis
```

#### Feature #14: Manual Incident Reanalysis
**Requires:** ANTHROPIC_API_KEY

```bash
# Get incident ID from previous test
INCIDENT_ID=1

# Trigger reanalysis
curl -X POST http://localhost:8000/incidents/$INCIDENT_ID/reanalyze

# Wait for Claude API
sleep 10

# Verify report updated
curl http://localhost:8000/incidents/$INCIDENT_ID | python3 -m json.tool
```

### Streamlit UI Features (12 tests)

All tests below require browser automation (puppeteer with working sandbox).

#### Test Script Template

```javascript
// Pseudo-code for puppeteer testing

// 1. Navigate to dashboard
await page.goto('http://localhost:8501');

// 2. Wait for Streamlit to load
await page.waitForSelector('.stApp');

// 3. Take initial screenshot
await page.screenshot({ path: 'dashboard-initial.png' });

// 4. Test specific feature (see individual tests below)
```

#### Feature #24: Dashboard Status Grid Display

**Expected Elements:**
- Environment tabs: "All", "Dev", "Staging", "Production"
- Status cards for each endpoint with:
  - Endpoint name
  - Status indicator (UP/DEGRADED/DOWN)
  - Last check timestamp
  - Response time
- Summary metrics row showing total/up/degraded/down counts

**Browser Test:**
```javascript
// Check environment tabs exist
const tabs = await page.$$('[data-testid="stTabs"] button');
console.log(`Found ${tabs.length} tabs (expect 4: All, Dev, Staging, Production)`);

// Check status cards rendered
const cards = await page.$$('[data-testid="stStatusCard"]');
console.log(`Found ${cards.length} endpoint cards`);

// Screenshot
await page.screenshot({ path: 'feature-24-status-grid.png' });
```

#### Feature #25: Environment Tab Filtering

**Test Steps:**
1. Create 2 dev endpoints and 2 production endpoints via API
2. Navigate to dashboard
3. Click "Dev" tab
4. Verify only 2 cards shown
5. Click "Production" tab
6. Verify only 2 cards shown

**Browser Test:**
```javascript
// Click Dev tab
await page.click('button:has-text("Dev")');
await page.waitForTimeout(1000); // Wait for Streamlit re-run

// Count visible cards
const devCards = await page.$$('[data-testid="stStatusCard"]');
console.log(`Dev tab shows ${devCards.length} endpoints (expect 2)`);

// Screenshot
await page.screenshot({ path: 'feature-25-dev-tab.png' });

// Click Production tab
await page.click('button:has-text("Production")');
await page.waitForTimeout(1000);

const prodCards = await page.$$('[data-testid="stStatusCard"]');
console.log(`Production tab shows ${prodCards.length} endpoints (expect 2)`);

// Screenshot
await page.screenshot({ path: 'feature-25-prod-tab.png' });
```

#### Feature #26: Response Time Chart

**Expected:**
- Plotly line chart showing response times over 24h
- X-axis: timestamps
- Y-axis: response time in ms
- Red dashed threshold line at max response time setting

**Browser Test:**
```javascript
// Wait for Plotly chart to render
await page.waitForSelector('.js-plotly-plot');

// Get chart element
const chart = await page.$('.js-plotly-plot');

// Screenshot chart area
await chart.screenshot({ path: 'feature-26-response-time-chart.png' });

// Verify threshold line visible (red dashed line in chart)
// This requires visual inspection of the screenshot
```

#### Feature #27: Incident Log Panel

**Expected:**
- Right sidebar or section showing incident history
- Open incidents at top with severity badges (LOW=blue, MEDIUM=orange, HIGH=red)
- Resolved incidents below (last 5)
- "View Claude Report" expander for each incident

**Browser Test:**
```javascript
// Scroll to incident log section
await page.evaluate(() => {
  document.querySelector('[data-testid="stSidebar"]')?.scrollIntoView();
});

// Screenshot incident log
await page.screenshot({ path: 'feature-27-incident-log.png' });

// Click "View Claude Report" expander
await page.click('[data-testid="stExpander"]:has-text("View Claude Report")');
await page.waitForTimeout(500);

// Screenshot expanded report
await page.screenshot({ path: 'feature-27-claude-report-expanded.png' });
```

#### Feature #28: Endpoint Detail Sidebar

**Expected:**
- Click endpoint card to open detail sidebar
- Sidebar shows:
  - SLA metrics (24h/7d/30d uptime %)
  - Check history table with pagination
  - Alert configuration form (email/Slack/desktop)

**Browser Test:**
```javascript
// Click first endpoint card
const firstCard = await page.$('[data-testid="stStatusCard"]');
await firstCard.click();
await page.waitForTimeout(1000);

// Wait for sidebar to open
await page.waitForSelector('[data-testid="stSidebar"]');

// Screenshot sidebar
await page.screenshot({ path: 'feature-28-endpoint-detail-sidebar.png' });

// Check SLA metrics visible
const slaMetrics = await page.$$('[data-testid="stMetric"]');
console.log(`Found ${slaMetrics.length} SLA metrics (expect 3: 24h, 7d, 30d)`);
```

#### Feature #29: Bulk Check Now Button

**Expected:**
- Button in environment tab view: "Bulk Check Now"
- Clicking triggers immediate checks for all endpoints in current environment filter

**Browser Test:**
```javascript
// Click "Staging" tab
await page.click('button:has-text("Staging")');
await page.waitForTimeout(1000);

// Click "Bulk Check Now" button
await page.click('button:has-text("Bulk Check Now")');

// Wait for checks to complete
await page.waitForTimeout(5000);

// Verify check counts increased via API
const response = await fetch('http://localhost:8000/checks?limit=10');
const checks = await response.json();
console.log('Latest checks:', checks);

// Screenshot after bulk check
await page.screenshot({ path: 'feature-29-bulk-check-complete.png' });
```

#### Feature #30: Comprehensive End-to-End Workflow

This is the full workflow test covering all features. See `feature_list.json` lines 340-356 for the complete 14-step test.

**Summary:**
1. Add endpoint via UI
2. Configure alerts
3. Trigger failure sequence (3 failures)
4. Verify incident opens
5. Wait for Claude report
6. Verify alert sent
7. Check UI shows incident
8. View Claude report in UI
9. Fix endpoint URL
10. Trigger 2 passing checks
11. Verify incident auto-closes
12. Verify resolved alert sent
13. Verify UI updates to show resolved incident

#### Features #33-37: Style Tests

These require visual inspection of screenshots:

**#33: Status Card Color-Coding**
- Green border/background for UP (#22C55E)
- Amber for DEGRADED (#F59E0B)
- Red for DOWN (#EF4444)

**#34: Severity Badges**
- LOW: blue (#3B82F6)
- MEDIUM: orange (#F97316)
- HIGH: red (#EF4444)

**#35: Response Time Chart Threshold Line**
- Red dashed line at configured threshold (#EF4444)

**#36: Dashboard Auto-Refresh**
- Dashboard refreshes every 60 seconds automatically
- No full page reload (uses st.rerun internally)

**#37: SLA Metrics Format**
- Uses st.metric component
- Large bold numbers
- Small labels above

## Running Tests on Compatible Environment

If you have a machine with working browser automation:

```bash
# 1. Clone/copy the project
git clone <repo>
cd apiwatcher_run1

# 2. Start services
./init.sh

# 3. Run puppeteer tests (create test-streamlit.js)
node test-streamlit.js

# 4. Review screenshots in ./screenshots/
ls -l screenshots/

# 5. Update feature_list.json for passing tests
# Change "passes": false → "passes": true
```

## Alternative: Docker Environment

To avoid VPS sandbox issues:

```dockerfile
FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    python3 python3-pip nodejs npm \
    chromium-browser \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . /app
WORKDIR /app

# Install dependencies
RUN pip3 install -r requirements.txt
RUN npm install -g puppeteer

# Run tests
CMD ["./init.sh"]
```

## Notes for Future Sessions

- The `.mcp.json` has been updated with `--no-sandbox` environment variable attempt
- This configuration change requires a new Claude Code session to take effect
- If browser automation works in next session, prioritize testing features #24-30 (functional)
- Then test features #33-37 (style/visual)
- Features #13-14 require ANTHROPIC_API_KEY to be set before testing
