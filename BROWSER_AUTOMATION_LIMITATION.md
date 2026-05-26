# Browser Automation Limitation on VPS

## Issue Summary

Puppeteer browser automation is **blocked** on this Hostinger VPS (Ubuntu 24.04) due to AppArmor security restrictions on unprivileged user namespaces.

**Impact**: 12 of 14 remaining tests require browser automation to verify Streamlit UI features.

## Error Message

```
[PID:PID:DATE:FATAL:zygote_host_impl_linux.cc(128)] No usable sandbox!
If you are running on Ubuntu 23.10+ or another Linux distro that has disabled unprivileged user namespaces with AppArmor, see https://chromium.googlesource.com/chromium/src/+/main/docs/security/apparmor-userns-restrictions.md
```

## Root Cause

Ubuntu 23.10+ (including 24.04) disabled unprivileged user namespaces for security. Chrome/Chromium requires sandboxing via user namespaces, which are now blocked by AppArmor.

## Attempted Solutions

### ❌ Attempt 1: .mcp.json Environment Variable (Session 6)

Created `.mcp.json` with:
```json
{
  "mcpServers": {
    "puppeteer": {
      "command": "npx",
      "args": ["puppeteer-mcp-server"],
      "env": {
        "PUPPETEER_ARGS": "--no-sandbox --disable-setuid-sandbox"
      }
    }
  }
}
```

**Result**: Failed. The `PUPPETEER_ARGS` environment variable is not recognized by `puppeteer-mcp-server`. Chrome still attempts to use sandboxing and fails.

### ❌ Attempt 2: Session Restart (Session 7)

Hypothesis: Session 6 couldn't restart MCP server, but Session 7 (new session) would inherit the .mcp.json configuration.

**Result**: Failed. Same error persists. Environment variable approach doesn't work.

## Why .mcp.json Didn't Work

The `puppeteer-mcp-server` MCP tool does not read custom environment variables like `PUPPETEER_ARGS`. The Chrome launch arguments need to be passed directly to the `puppeteer.launch()` call within the MCP server code, which we cannot modify.

## Working Solutions

### ✅ Solution 1: Docker Container (Recommended)

Run APIWatcher in Docker with `--security-opt seccomp=unconfined`:

```bash
# Create Dockerfile
cat > Dockerfile << 'EOF'
FROM python:3.11
RUN apt-get update && apt-get install -y \
    chromium chromium-driver \
    libnspr4 libnss3 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libasound2
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["./init.sh"]
EOF

# Build and run
docker build -t apiwatcher .
docker run --security-opt seccomp=unconfined -p 8000:8000 -p 8501:8501 apiwatcher
```

### ✅ Solution 2: Ubuntu 22.04 Environment

Downgrade to Ubuntu 22.04 (or earlier) which doesn't have AppArmor user namespace restrictions.

### ✅ Solution 3: Local Development Machine

Test Streamlit UI features on a local machine (Mac, Windows, Ubuntu 22.04) where puppeteer works normally.

### ✅ Solution 4: System-Level Configuration (Requires Root)

**WARNING**: This disables important security features. Only for development/testing VPS.

```bash
# Option A: Disable AppArmor for unprivileged user namespaces
sudo sysctl -w kernel.apparmor_restrict_unprivileged_userns=0

# Option B: Allow Chrome/Chromium specifically (safer)
sudo aa-complain /usr/bin/chromium-browser
```

## Alternative Testing Methods (Without Browser)

### Method 1: curl + HTML Inspection

```bash
# Fetch Streamlit HTML
curl -s http://localhost:8501 > /tmp/streamlit_page.html

# Check for expected elements
grep -q "APIWatcher" /tmp/streamlit_page.html && echo "✅ Title present"
grep -q "stApp" /tmp/streamlit_page.html && echo "✅ Streamlit app loaded"
```

**Limitation**: Cannot verify dynamic content, charts, or user interactions.

### Method 2: Backend Data Verification

Instead of checking the UI visually, verify the **data** the UI displays:

```bash
# Verify status grid data (what Streamlit would show)
curl -s http://localhost:8000/endpoints | jq '.[] | {name, enabled}'

# Verify chart data (what Plotly would display)
curl -s http://localhost:8000/checks/1 | jq '[.[] | .response_time] | @json'

# Verify incident log data
curl -s http://localhost:8000/incidents | jq '.[] | {endpoint_id, severity, started_at}'
```

**Limitation**: Cannot verify UI styling, color-coding, or visual layout.

### Method 3: Streamlit CLI Testing

```bash
# Check Streamlit loads without errors
timeout 10 streamlit run watcher/dashboard.py --server.port 8502 > /tmp/streamlit_test.log 2>&1 &
sleep 5
grep -i "error\|exception\|traceback" /tmp/streamlit_test.log && echo "❌ Errors found" || echo "✅ No errors"
kill %1
```

## Recommendations for Future Sessions

1. **Immediate**: Use Alternative Testing Method 2 (Backend Data Verification) to verify Features #24-30, #33-37 functionally
2. **Short-term**: Test Streamlit UI on local development machine with working browser automation
3. **Long-term**: Set up Docker development environment with `--security-opt seccomp=unconfined` for consistent VPS testing

## Features Blocked by This Issue

| Feature # | Description | Workaround Available? |
|-----------|-------------|----------------------|
| #13-14 | Claude AI reports | ❌ (needs API key) |
| #24 | Status grid display | ✅ (backend verification) |
| #25 | Environment tab filtering | ✅ (backend verification) |
| #26 | Response time chart | ✅ (backend verification) |
| #27 | Incident log panel | ✅ (backend verification) |
| #28 | Endpoint detail sidebar | ✅ (backend verification) |
| #29 | Bulk check button | ✅ (backend verification) |
| #30 | End-to-end workflow | ❌ (partial - can't verify UI) |
| #33 | Status card color-coding | ❌ (visual only) |
| #34 | Severity badge colors | ❌ (visual only) |
| #35 | Threshold line on chart | ❌ (visual only) |
| #36 | Dashboard auto-refresh | ✅ (can verify with logs) |
| #37 | SLA metric display format | ❌ (visual only) |
| #40 | Comprehensive e2e | ❌ (needs both browser + API key) |

**Total**: 6 features can be verified without browser (backend data), 8 features require visual inspection or API key.

## Session 7 Status

- ✅ Confirmed browser automation still blocked
- ✅ Verified all 26 passing backend features working (no regressions)
- ✅ Documented comprehensive solutions and workarounds
- ⏭️ Next: Implement backend verification tests for Features #24-29, #36

---

**Last Updated**: Session 7 (2026-05-26)
**Next Action**: Use backend data verification method to test functional aspects of Streamlit features
