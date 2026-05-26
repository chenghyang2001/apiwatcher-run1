"""
Claude AI incident report generation using Anthropic SDK.
"""

import os
import json
from typing import Optional
from sqlalchemy.orm import Session
from anthropic import Anthropic
from .models import Endpoint, Incident, Check


def get_api_key() -> Optional[str]:
    """
    Get Anthropic API key from environment or /tmp/api-key file.

    Returns:
        API key string or None if not found
    """
    # First try environment variable
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if api_key:
        return api_key

    # Try reading from /tmp/api-key
    try:
        with open("/tmp/api-key", "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


async def generate_report(endpoint: Endpoint, incident: Incident, db: Session) -> bool:
    """
    Generate Claude AI incident report and store in incident.claude_report.

    Args:
        endpoint: Endpoint instance
        incident: Incident instance
        db: Database session

    Returns:
        True if report generated successfully, False otherwise
    """
    api_key = get_api_key()
    if not api_key:
        print("⚠ ANTHROPIC_API_KEY not set, skipping Claude report generation")
        return False

    try:
        # Fetch last 20 check results for context
        recent_checks = (
            db.query(Check)
            .filter(Check.endpoint_id == endpoint.id)
            .order_by(Check.id.desc())
            .limit(20)
            .all()
        )

        # Build check history as JSON
        check_history = []
        for check in reversed(recent_checks):  # Oldest first
            check_history.append({
                "timestamp": check.checked_at.isoformat(),
                "passed": check.passed,
                "status_code": check.status_code,
                "response_time_ms": check.response_time,
                "error_message": check.error_message
            })

        # Build Claude prompt
        prompt = f"""You are analyzing an API endpoint failure incident. Please provide a clear, plain-English incident report.

**Endpoint Details:**
- Name: {endpoint.name}
- URL: {endpoint.url}
- Method: {endpoint.method}
- Expected Status: {endpoint.expected_status}

**Incident Details:**
- Started: {incident.started_at.isoformat()}
- Severity: {incident.severity}
- Consecutive Failures: {incident.failure_count}

**Recent Check History (last 20 checks, oldest to newest):**
```json
{json.dumps(check_history, indent=2)}
```

Please analyze this incident and provide:

1. **Summary**: What failed and for how long?
2. **Last Successful Check**: When was the last time this endpoint worked?
3. **Error Pattern Analysis**: Are the failures due to timeouts, 5xx errors, 4xx errors, or connection issues?
4. **Probable Root Causes**: List 2-3 likely causes with estimated likelihood percentage (e.g., "Server overload (70%)")
5. **Suggested Remediation**: What immediate steps should the team take?

Write in clear, non-technical language suitable for both developers and managers.
"""

        # Call Claude API
        print(f"Generating Claude AI report for incident {incident.id}...")
        client = Anthropic(api_key=api_key)

        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        # Extract report text
        report_text = message.content[0].text

        # Store in database
        incident.claude_report = report_text
        db.commit()

        print(f"✓ Claude AI report generated for incident {incident.id}")
        return True

    except Exception as e:
        print(f"Error generating Claude report: {e}")
        incident.claude_report = f"Error generating report: {str(e)}"
        db.commit()
        return False


async def reanalyze_incident(incident_id: int, db: Session) -> bool:
    """
    Regenerate Claude AI report for an existing incident.

    Args:
        incident_id: ID of the incident to reanalyze
        db: Database session

    Returns:
        True if successful, False otherwise
    """
    incident = db.query(Incident).filter(Incident.id == incident_id).first()
    if not incident:
        return False

    endpoint = db.query(Endpoint).filter(Endpoint.id == incident.endpoint_id).first()
    if not endpoint:
        return False

    # Clear existing report
    incident.claude_report = None
    db.commit()

    # Generate new report
    return await generate_report(endpoint, incident, db)
