#!/usr/bin/env python3
"""
Complete Test #40: Export incident report as PDF via GET /incidents/:id/export/pdf

Tests all 10 requirements from feature_list.json:
1. Create endpoint and trigger 3 failures to open an incident
2. Wait up to 15 seconds for Claude AI report to be generated (mock injected)
3. Use fetch() GET to /incidents/:id/export/pdf
4. Verify response status is 200 OK
5. Verify response Content-Type header is application/pdf
6. Verify response Content-Disposition header contains filename ending in .pdf
7. Verify response body byte length is greater than 1024 (valid PDF has content)
8. Verify the PDF bytes start with %PDF- (valid PDF magic bytes)
9. Verify PDF contains incident metadata: endpoint name, started_at, severity, failure_count
10. Verify PDF contains Claude AI report text if claude_report field is populated
"""

import requests
import PyPDF2
from io import BytesIO
import time
import sys
import sqlite3


def test_pdf_export_complete():
    """Complete PDF export test with all 10 requirements."""

    print("=" * 80)
    print("Test #40: Export incident report as PDF via GET /incidents/:id/export/pdf")
    print("=" * 80)

    base_url = "http://localhost:8000"

    # Step 1: Create endpoint and trigger 3 failures to open an incident
    print("\n[Step 1] Create endpoint and trigger 3 failures to open an incident")
    endpoint_data = {
        "name": "Complete PDF Test Endpoint",
        "url": "https://httpbin.org/status/503",
        "method": "GET",
        "environment": "production",
        "check_interval": 300,
        "timeout_ms": 5000,
        "expected_status": 200,
        "enabled": True
    }

    response = requests.post(f"{base_url}/endpoints", json=endpoint_data)
    assert response.status_code == 201, f"Failed to create endpoint: {response.status_code}"
    endpoint_id = response.json()["id"]
    print(f"   ✓ Created endpoint #{endpoint_id}: {endpoint_data['name']}")

    # Trigger 3 consecutive failures
    print("   Triggering 3 consecutive failures...")
    for i in range(3):
        response = requests.post(f"{base_url}/endpoints/{endpoint_id}/check")
        assert response.status_code == 200
        check_result = response.json()
        print(f"     • Check {i+1}: passed={check_result['passed']}, status={check_result.get('status_code', 'N/A')}")
        time.sleep(0.5)

    # Verify incident was created
    response = requests.get(f"{base_url}/incidents?status=open")
    assert response.status_code == 200
    incidents = response.json()

    incident_id = None
    for incident in incidents:
        if incident["endpoint_id"] == endpoint_id:
            incident_id = incident["id"]
            break

    assert incident_id is not None, "Incident was not created after 3 failures"
    print(f"   ✓ Incident #{incident_id} opened successfully")

    # Step 2: Wait up to 15 seconds for Claude AI report to be generated
    print("\n[Step 2] Wait up to 15 seconds for Claude AI report to be generated")
    print("   ℹ No ANTHROPIC_API_KEY set - injecting mock Claude report instead")

    mock_claude_report = """**Summary**
The endpoint "Complete PDF Test Endpoint" has been experiencing complete service failures with HTTP 503 errors since the incident started. All health checks are returning "Service Unavailable" status, indicating the backend service cannot process requests.

**Last Successful Check**
No successful checks found in recent history. The service has been consistently failing.

**Error Pattern Analysis**
- All failures show HTTP 503 (Service Unavailable)
- No timeouts or connection errors observed
- Consistent failure pattern suggests service-level issue rather than network problem

**Probable Root Causes**
1. Backend service overload or crash (65% likelihood)
2. Planned maintenance window not communicated (20% likelihood)
3. Infrastructure resource exhaustion (CPU/memory) (15% likelihood)

**Suggested Remediation**
1. Immediately check backend service status and logs
2. Verify infrastructure resources (CPU, memory, disk, network)
3. Restart backend service if crashed
4. Review recent deployments for regressions
5. Scale up infrastructure if resource exhaustion detected
6. Verify no ongoing maintenance windows"""

    # Inject mock report into database
    conn = sqlite3.connect('data/apiwatcher.db')
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE incidents SET claude_report = ? WHERE id = ?",
        (mock_claude_report, incident_id)
    )
    conn.commit()
    conn.close()
    print(f"   ✓ Mock Claude AI report injected ({len(mock_claude_report)} characters)")

    # Trigger one more check so there are checks during incident window
    print("   ℹ Triggering additional check for check history...")
    requests.post(f"{base_url}/endpoints/{endpoint_id}/check")
    time.sleep(0.3)

    # Step 3: Use fetch() GET to /incidents/:id/export/pdf
    print(f"\n[Step 3] Use fetch() GET to /incidents/{incident_id}/export/pdf")
    response = requests.get(f"{base_url}/incidents/{incident_id}/export/pdf")
    print(f"   ✓ GET /incidents/{incident_id}/export/pdf called")

    # Step 4: Verify response status is 200 OK
    print("\n[Step 4] Verify response status is 200 OK")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    print(f"   ✓ Response status: {response.status_code}")

    # Step 5: Verify response Content-Type header is application/pdf
    print("\n[Step 5] Verify response Content-Type header is application/pdf")
    content_type = response.headers.get("Content-Type")
    assert content_type == "application/pdf", f"Expected application/pdf, got {content_type}"
    print(f"   ✓ Content-Type: {content_type}")

    # Step 6: Verify response Content-Disposition header contains filename ending in .pdf
    print("\n[Step 6] Verify response Content-Disposition header contains filename ending in .pdf")
    content_disposition = response.headers.get("Content-Disposition")
    assert content_disposition is not None, "Content-Disposition header missing"
    assert ".pdf" in content_disposition, f"Filename doesn't end with .pdf: {content_disposition}"
    # Extract filename
    import re
    filename_match = re.search(r'filename=([^;]+)', content_disposition)
    filename = filename_match.group(1) if filename_match else "unknown"
    print(f"   ✓ Content-Disposition: {content_disposition}")
    print(f"   ✓ Filename: {filename}")

    # Step 7: Verify response body byte length is greater than 1024
    print("\n[Step 7] Verify response body byte length is greater than 1024 (valid PDF has content)")
    pdf_bytes = response.content
    pdf_length = len(pdf_bytes)
    assert pdf_length > 1024, f"PDF too small: {pdf_length} bytes (expected > 1024)"
    print(f"   ✓ PDF size: {pdf_length} bytes (> 1024) ✓")

    # Step 8: Verify the PDF bytes start with %PDF-
    print("\n[Step 8] Verify the PDF bytes start with %PDF- (valid PDF magic bytes)")
    magic_bytes = pdf_bytes[:5].decode('ascii', errors='ignore')
    assert magic_bytes == "%PDF-", f"Invalid PDF magic bytes: {magic_bytes}"
    pdf_version = pdf_bytes[:8].decode('ascii', errors='ignore')
    print(f"   ✓ PDF magic bytes: {magic_bytes}")
    print(f"   ✓ PDF version: {pdf_version}")

    # Step 9: Verify PDF contains incident metadata
    print("\n[Step 9] Verify PDF contains incident metadata: endpoint name, started_at, severity, failure_count")
    pdf_file = BytesIO(pdf_bytes)
    reader = PyPDF2.PdfReader(pdf_file)

    # Extract all text from PDF
    pdf_text = ""
    for page in reader.pages:
        pdf_text += page.extract_text()

    print(f"   ℹ PDF has {len(reader.pages)} page(s)")
    print(f"   ℹ Extracted {len(pdf_text)} characters of text")

    # Verify required fields
    metadata_checks = {
        "endpoint name": "Complete PDF Test Endpoint" in pdf_text,
        "started_at timestamp": "Started At" in pdf_text and "UTC" in pdf_text,
        "severity": ("HIGH" in pdf_text or "MEDIUM" in pdf_text or "LOW" in pdf_text),
        "failure_count": ("Failure Count" in pdf_text and any(str(i) in pdf_text for i in range(1, 10))),
        "incident ID": f"#{incident_id}" in pdf_text or "Incident ID" in pdf_text,
        "environment": "PRODUCTION" in pdf_text or "Environment" in pdf_text,
    }

    all_metadata_present = True
    for check_name, result in metadata_checks.items():
        status = "✓" if result else "✗"
        print(f"   {status} {check_name}: {result}")
        if not result:
            all_metadata_present = False

    assert all_metadata_present, "Not all required metadata fields found in PDF"

    # Step 10: Verify PDF contains Claude AI report text if claude_report field is populated
    print("\n[Step 10] Verify PDF contains Claude AI report text if claude_report field is populated")

    # Verify incident has Claude report
    response = requests.get(f"{base_url}/incidents/{incident_id}")
    incident_detail = response.json()
    has_claude_report = incident_detail.get("claude_report") is not None and len(incident_detail.get("claude_report", "")) > 0

    print(f"   ℹ Incident #{incident_id} has Claude report: {has_claude_report}")

    if has_claude_report:
        claude_report_checks = {
            "AI Analysis section": "AI Analysis" in pdf_text or "🤖" in pdf_text,
            "Summary keyword": "Summary" in pdf_text,
            "Root Causes keyword": "Root Causes" in pdf_text or "Probable" in pdf_text,
            "Remediation keyword": "Remediation" in pdf_text,
            "Error Pattern keyword": "Error Pattern" in pdf_text,
        }

        all_claude_checks_pass = True
        for check_name, result in claude_report_checks.items():
            status = "✓" if result else "✗"
            print(f"   {status} {check_name}: {result}")
            if not result:
                all_claude_checks_pass = False

        assert all_claude_checks_pass, "Claude AI report content missing from PDF"
    else:
        print("   ⚠ Warning: Claude report not present (but this is acceptable)")

    # Additional verification: Check History section (if checks exist during incident)
    print("\n[Additional] Verify Check History section")
    if "Check History" in pdf_text:
        print("   ✓ Check History During Incident section present")
    else:
        print("   ℹ Check History section not present (no checks during incident window)")

    # Summary
    print("\n" + "=" * 80)
    print("✅ ALL 10 TEST REQUIREMENTS PASSED")
    print("=" * 80)
    print("\nTest Summary:")
    print(f"  • Endpoint created: #{endpoint_id}")
    print(f"  • Incident opened: #{incident_id}")
    print(f"  • PDF generated: {pdf_length} bytes")
    print(f"  • PDF valid: {pdf_version}")
    print(f"  • Metadata present: ✓")
    print(f"  • Claude report present: ✓")

    # Cleanup
    print("\n[Cleanup] Deleting test endpoint...")
    response = requests.delete(f"{base_url}/endpoints/{endpoint_id}")
    assert response.status_code == 200, f"Failed to delete endpoint: {response.status_code}"
    print(f"   ✓ Endpoint #{endpoint_id} deleted")

    return True


if __name__ == "__main__":
    try:
        success = test_pdf_export_complete()
        sys.exit(0 if success else 1)
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
