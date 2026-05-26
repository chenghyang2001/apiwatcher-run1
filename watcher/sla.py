"""
SLA uptime calculation and CSV export.
"""

import io
import csv
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_
from .models import Check


def calculate_uptime(endpoint_id: int, window_hours: int, db: Session) -> float:
    """
    Calculate uptime percentage for an endpoint over a time window.

    Formula: (passing_checks / total_checks) * 100

    Args:
        endpoint_id: ID of the endpoint
        window_hours: Time window in hours (24, 168=7d, 720=30d)
        db: Database session

    Returns:
        Uptime percentage (0.0 to 100.0)
    """
    cutoff_time = datetime.utcnow() - timedelta(hours=window_hours)

    # Query checks within window
    checks = (
        db.query(Check)
        .filter(
            and_(
                Check.endpoint_id == endpoint_id,
                Check.checked_at >= cutoff_time
            )
        )
        .all()
    )

    if not checks:
        return 100.0  # No data = assume up

    total = len(checks)
    passed = sum(1 for check in checks if check.passed)

    uptime = (passed / total) * 100.0
    return round(uptime, 2)


def export_sla_csv(endpoint_id: int, db: Session) -> str:
    """
    Export SLA history as CSV string.

    Args:
        endpoint_id: ID of the endpoint
        db: Database session

    Returns:
        CSV string with columns: date, uptime_24h, uptime_7d, uptime_30d
    """
    output = io.StringIO()
    writer = csv.writer(output)

    # Write header
    writer.writerow(['date', 'uptime_24h', 'uptime_7d', 'uptime_30d'])

    # For simplicity, we'll just export current values
    # In production, you'd calculate historical SLA for past dates
    today = datetime.utcnow().date()

    uptime_24h = calculate_uptime(endpoint_id, 24, db)
    uptime_7d = calculate_uptime(endpoint_id, 168, db)
    uptime_30d = calculate_uptime(endpoint_id, 720, db)

    writer.writerow([today, f"{uptime_24h}%", f"{uptime_7d}%", f"{uptime_30d}%"])

    return output.getvalue()


def check_sla_breach(endpoint, uptime: float) -> bool:
    """
    Check if uptime is below SLA target.

    Args:
        endpoint: Endpoint instance with sla_target
        uptime: Current uptime percentage

    Returns:
        True if SLA is breached (uptime < target)
    """
    return uptime < endpoint.sla_target
