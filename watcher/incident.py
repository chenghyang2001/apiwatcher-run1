"""
Incident detection and management logic.

Rules:
- Open incident: 3 consecutive check failures for same endpoint
- Close incident: 2 consecutive passing checks after incident start
- Severity: LOW (slow response), MEDIUM (partial failure), HIGH (complete down)
"""

from datetime import datetime
from sqlalchemy.orm import Session
from .models import Check, Incident, Endpoint


def determine_severity(checks: list[Check]) -> str:
    """
    Determine incident severity based on recent check failures.

    Args:
        checks: List of recent failed checks

    Returns:
        Severity level: "LOW", "MEDIUM", or "HIGH"
    """
    if not checks:
        return "MEDIUM"

    # Check if all failures are timeout-related (HIGH severity)
    timeout_count = sum(1 for c in checks if c.error_message and "timeout" in c.error_message.lower())
    if timeout_count == len(checks):
        return "HIGH"

    # Check for 5xx errors (HIGH severity)
    server_error_count = sum(1 for c in checks if c.status_code and c.status_code >= 500)
    if server_error_count >= len(checks) // 2:
        return "HIGH"

    # Check for 4xx errors (MEDIUM severity)
    client_error_count = sum(1 for c in checks if c.status_code and 400 <= c.status_code < 500)
    if client_error_count >= len(checks) // 2:
        return "MEDIUM"

    # Check for slow responses (LOW severity)
    slow_count = sum(1 for c in checks if c.response_time and c.response_time > 2000)
    if slow_count >= len(checks) // 2:
        return "LOW"

    return "MEDIUM"


async def evaluate_incident(endpoint_id: int, db: Session):
    """
    Evaluate incident detection logic after a check is saved.

    Rules:
    1. Open incident if last 3 checks all failed and no open incident exists
    2. Close incident if last 2 checks passed and an open incident exists
    3. Trigger alerts on incident open/close

    Args:
        endpoint_id: ID of the endpoint to evaluate
        db: Database session
    """
    # Fetch endpoint
    endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
    if not endpoint:
        return

    # Get last 3 checks
    recent_checks = (
        db.query(Check)
        .filter(Check.endpoint_id == endpoint_id)
        .order_by(Check.id.desc())
        .limit(3)
        .all()
    )

    if len(recent_checks) < 3:
        # Not enough data yet
        return

    # Check for open incident
    open_incident = (
        db.query(Incident)
        .filter(Incident.endpoint_id == endpoint_id, Incident.resolved_at == None)
        .first()
    )

    # Rule 1: Open incident if last 3 checks all failed
    if not open_incident:
        all_failed = all(not check.passed for check in recent_checks)
        if all_failed:
            severity = determine_severity(recent_checks)
            incident = Incident(
                endpoint_id=endpoint_id,
                started_at=datetime.utcnow(),
                failure_count=3,
                severity=severity
            )
            db.add(incident)
            db.commit()
            db.refresh(incident)

            print(f"✗ INCIDENT OPENED: endpoint_id={endpoint_id}, incident_id={incident.id}, severity={severity}")

            # Trigger alerts (import here to avoid circular dependency)
            from .alerter import send_incident_alerts
            await send_incident_alerts(endpoint, incident, db, event_type="incident_opened")

            # Trigger Claude AI report generation (async, non-blocking)
            from .claude_reporter import generate_report
            asyncio.create_task(generate_report(endpoint, incident, db))

            return

    # Rule 2: Close incident if last 2 checks passed
    if open_incident:
        last_two_checks = recent_checks[:2]
        if len(last_two_checks) >= 2:
            all_passed = all(check.passed for check in last_two_checks)
            if all_passed:
                # Calculate duration
                duration = (datetime.utcnow() - open_incident.started_at).total_seconds() / 60
                open_incident.resolved_at = datetime.utcnow()
                open_incident.duration_mins = int(duration)
                db.commit()

                print(f"✓ INCIDENT RESOLVED: endpoint_id={endpoint_id}, incident_id={open_incident.id}, "
                      f"duration={open_incident.duration_mins}min")

                # Trigger resolved alerts
                from .alerter import send_incident_alerts
                await send_incident_alerts(endpoint, open_incident, db, event_type="incident_resolved")

                return

        # Incident still open, increment failure count
        open_incident.failure_count += 1
        db.commit()


# Import asyncio for async tasks
import asyncio
