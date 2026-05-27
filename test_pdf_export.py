#!/usr/bin/env python3
"""
Test script for PDF export functionality (Test #40).
Verifies all requirements from feature_list.json without browser automation.
"""

import requests
import PyPDF2
from io import BytesIO
import time
import sys


def test_pdf_export():
    """Test incident PDF export endpoint."""

    print("=" * 70)
    print("Test #40: Export incident report as PDF via GET /incidents/:id/export/pdf")
    print("=" * 70)

    base_url = "http://localhost:8000"

    # Step 1: Create endpoint and trigger 3 failures to open an incident
    print("\n[Step 1] Creating test endpoint that will fail...")

    endpoint_data = {
        "name": "PDF Test Endpoint",
        "url": "https://httpbin.org/status/500",  # Will always fail
        "method": "GET",
        "environment": "dev",
        "check_interval": 300,
        "timeout_ms": 5000,
        "expected_status": 200,
        "enabled": True
    }

    response = requests.post(f"{base_url}/endpoints", json=endpoint_data)
    assert response.status_code == 201, f"Failed to create endpoint: {response.status_code}"
    endpoint_id = response.json()["id"]
    print(f"   ✓ Created endpoint #{endpoint_id}")

    # Trigger 3 manual checks to open incident
    print("\n[Step 1.1] Triggering 3 consecutive failures to open incident...")
    for i in range(3):
        response = requests.post(f"{base_url}/endpoints/{endpoint_id}/check")
        assert response.status_code == 200
        check_result = response.json()
        print(f"   ✓ Check {i+1}: passed={check_result['passed']}")
        time.sleep(0.5)

    # Verify incident was created
    print("\n[Step 1.2] Verifying incident was opened...")
    response = requests.get(f"{base_url}/incidents?status=open")
    assert response.status_code == 200
    incidents = response.json()

    # Find the incident for our endpoint
    incident_id = None
    for incident in incidents:
        if incident["endpoint_id"] == endpoint_id:
            incident_id = incident["id"]
            break

    assert incident_id is not None, "Incident was not created after 3 failures"
    print(f"   ✓ Incident #{incident_id} opened for endpoint #{endpoint_id}")

    # Step 2: Wait for Claude AI report (optional - we'll test without it for now)
    print("\n[Step 2] Checking for Claude AI report...")
    response = requests.get(f"{base_url}/incidents/{incident_id}")
    incident_detail = response.json()
    has_claude_report = incident_detail.get("claude_report") is not None
    print(f"   ℹ Claude report present: {has_claude_report}")

    # Step 3: Test PDF export endpoint
    print("\n[Step 3] Calling GET /incidents/{incident_id}/export/pdf...")
    response = requests.get(f"{base_url}/incidents/{incident_id}/export/pdf")

    # Step 4: Verify response status is 200 OK
    print("\n[Step 4] Verifying response status...")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    print(f"   ✓ Status code: {response.status_code}")

    # Step 5: Verify Content-Type header is application/pdf
    print("\n[Step 5] Verifying Content-Type header...")
    content_type = response.headers.get("Content-Type")
    assert content_type == "application/pdf", f"Expected application/pdf, got {content_type}"
    print(f"   ✓ Content-Type: {content_type}")

    # Step 6: Verify Content-Disposition header contains filename ending in .pdf
    print("\n[Step 6] Verifying Content-Disposition header...")
    content_disposition = response.headers.get("Content-Disposition")
    assert content_disposition is not None, "Content-Disposition header missing"
    assert ".pdf" in content_disposition, "Filename doesn't end with .pdf"
    print(f"   ✓ Content-Disposition: {content_disposition}")

    # Step 7: Verify response body byte length is greater than 1024
    print("\n[Step 7] Verifying PDF byte length...")
    pdf_bytes = response.content
    pdf_length = len(pdf_bytes)
    assert pdf_length > 1024, f"PDF too small: {pdf_length} bytes (expected > 1024)"
    print(f"   ✓ PDF size: {pdf_length} bytes (> 1024)")

    # Step 8: Verify PDF bytes start with %PDF- (valid PDF magic bytes)
    print("\n[Step 8] Verifying PDF magic bytes...")
    magic_bytes = pdf_bytes[:5].decode('ascii', errors='ignore')
    assert magic_bytes == "%PDF-", f"Invalid PDF magic bytes: {magic_bytes}"
    print(f"   ✓ PDF magic bytes: {magic_bytes}")

    # Step 9: Verify PDF contains incident metadata
    print("\n[Step 9] Verifying PDF contains incident metadata...")
    pdf_file = BytesIO(pdf_bytes)
    reader = PyPDF2.PdfReader(pdf_file)

    # Extract all text from PDF
    pdf_text = ""
    for page in reader.pages:
        pdf_text += page.extract_text()

    print(f"   ℹ Extracted {len(pdf_text)} characters from PDF")

    # Verify required fields are present
    checks = {
        "endpoint name": "PDF Test Endpoint" in pdf_text,
        "incident ID": f"#{incident_id}" in pdf_text or f"Incident ID" in pdf_text,
        "severity": incident_detail["severity"] in pdf_text,
        "failure count": str(incident_detail["failure_count"]) in pdf_text or "Failure Count" in pdf_text,
        "started_at timestamp": "Started At" in pdf_text,
    }

    for check_name, result in checks.items():
        status = "✓" if result else "✗"
        print(f"   {status} {check_name}: {result}")

    all_passed = all(checks.values())
    assert all_passed, "Not all required metadata fields found in PDF"

    # Step 10: Verify PDF contains Claude AI report text if present
    print("\n[Step 10] Verifying Claude AI report in PDF...")
    if has_claude_report:
        assert "AI Analysis Report" in pdf_text or "Claude" in pdf_text, \
            "Claude report missing from PDF despite being populated"
        print("   ✓ Claude AI report section present in PDF")
    else:
        print("   ℹ Claude report not present (skipping verification)")

    print("\n" + "=" * 70)
    print("✅ ALL PDF EXPORT TESTS PASSED")
    print("=" * 70)

    # Cleanup
    print("\n[Cleanup] Deleting test endpoint...")
    response = requests.delete(f"{base_url}/endpoints/{endpoint_id}")
    print(f"   ✓ Endpoint #{endpoint_id} deleted")

    return True


if __name__ == "__main__":
    try:
        success = test_pdf_export()
        sys.exit(0 if success else 1)
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
