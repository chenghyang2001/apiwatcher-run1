#!/usr/bin/env python3
"""
Test PDF export with Claude AI report included.
"""

import requests
import PyPDF2
from io import BytesIO
import time
import sys
import sqlite3


def test_pdf_with_claude_report():
    """Test PDF export with Claude AI report."""

    print("=" * 70)
    print("Test #40 (Part 2): PDF Export with Claude AI Report")
    print("=" * 70)

    base_url = "http://localhost:8000"

    # Create endpoint that will fail
    print("\n[Step 1] Creating test endpoint...")
    endpoint_data = {
        "name": "Claude Report Test",
        "url": "https://httpbin.org/status/503",
        "method": "GET",
        "environment": "production",
        "check_interval": 300,
        "timeout_ms": 5000,
        "expected_status": 200,
        "enabled": True
    }

    response = requests.post(f"{base_url}/endpoints", json=endpoint_data)
    assert response.status_code == 201
    endpoint_id = response.json()["id"]
    print(f"   ✓ Created endpoint #{endpoint_id}")

    # Trigger 3 failures to open incident
    print("\n[Step 2] Triggering failures to open incident...")
    for i in range(3):
        response = requests.post(f"{base_url}/endpoints/{endpoint_id}/check")
        assert response.status_code == 200
        time.sleep(0.5)

    # Get incident ID
    response = requests.get(f"{base_url}/incidents?status=open")
    incidents = response.json()
    incident_id = None
    for incident in incidents:
        if incident["endpoint_id"] == endpoint_id:
            incident_id = incident["id"]
            break

    assert incident_id is not None
    print(f"   ✓ Incident #{incident_id} opened")

    # Manually inject a mock Claude report into the database
    print("\n[Step 3] Injecting mock Claude AI report...")
    mock_report = """**Summary**
The API endpoint "Claude Report Test" has been experiencing complete outages with 503 Service Unavailable errors since {start_time}. This indicates the backend service is currently unable to handle requests.

**Last Successful Check**
No successful checks recorded in recent history - the service has been consistently failing.

**Error Pattern Analysis**
All failures show HTTP 503 status codes, which typically indicate:
- Service temporarily overloaded
- Service undergoing maintenance
- Backend workers unavailable

**Probable Root Causes**
1. Backend service overload or crash (60%)
2. Planned/unplanned maintenance window (25%)
3. Infrastructure resource exhaustion (15%)

**Suggested Remediation**
1. Check backend service status and restart if needed
2. Verify infrastructure resources (CPU, memory, connections)
3. Review recent deployments for regressions
4. Scale up backend capacity if under heavy load
5. Contact hosting provider if infrastructure issue suspected"""

    # Update database directly
    conn = sqlite3.connect('data/apiwatcher.db')
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE incidents SET claude_report = ? WHERE id = ?",
        (mock_report, incident_id)
    )
    conn.commit()
    conn.close()
    print(f"   ✓ Mock Claude report injected into incident #{incident_id}")

    # Export PDF
    print("\n[Step 4] Exporting PDF with Claude report...")
    response = requests.get(f"{base_url}/incidents/{incident_id}/export/pdf")

    # Verify response
    assert response.status_code == 200
    assert response.headers.get("Content-Type") == "application/pdf"
    print(f"   ✓ PDF exported successfully")

    # Parse PDF
    pdf_bytes = response.content
    pdf_file = BytesIO(pdf_bytes)
    reader = PyPDF2.PdfReader(pdf_file)

    # Extract text
    pdf_text = ""
    for page in reader.pages:
        pdf_text += page.extract_text()

    print(f"\n[Step 5] Verifying PDF content...")
    print(f"   ℹ PDF length: {len(pdf_bytes)} bytes")
    print(f"   ℹ Extracted text length: {len(pdf_text)} characters")

    # Verify required elements
    checks = {
        "Incident metadata present": "Incident Details" in pdf_text,
        "Endpoint name present": "Claude Report Test" in pdf_text,
        "Severity present": "Severity" in pdf_text,
        "AI Analysis section present": "AI Analysis" in pdf_text or "🤖" in pdf_text,
        "Summary section present": "Summary" in pdf_text,
        "Root causes present": "Root Causes" in pdf_text or "Probable" in pdf_text,
        "Remediation present": "Remediation" in pdf_text,
        "Check history present": "Check History" in pdf_text,
    }

    all_passed = True
    for check_name, result in checks.items():
        status = "✓" if result else "✗"
        print(f"   {status} {check_name}")
        if not result:
            all_passed = False

    # Cleanup
    print("\n[Cleanup] Deleting test endpoint...")
    response = requests.delete(f"{base_url}/endpoints/{endpoint_id}")
    print(f"   ✓ Endpoint #{endpoint_id} deleted")

    if all_passed:
        print("\n" + "=" * 70)
        print("✅ PDF WITH CLAUDE REPORT TEST PASSED")
        print("=" * 70)
        return True
    else:
        print("\n" + "=" * 70)
        print("❌ SOME CHECKS FAILED")
        print("=" * 70)
        print("\n[Debug] PDF Text Sample:")
        print(pdf_text[:500])
        return False


if __name__ == "__main__":
    try:
        success = test_pdf_with_claude_report()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
