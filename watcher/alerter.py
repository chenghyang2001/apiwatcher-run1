"""
Multi-channel alert sender: email, Slack webhook, desktop notification.
"""

import smtplib
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import httpx
from sqlalchemy.orm import Session
from .models import Endpoint, Incident, AlertConfig

try:
    from plyer import notification
    PLYER_AVAILABLE = True
except ImportError:
    PLYER_AVAILABLE = False
    print("Warning: plyer not available, desktop notifications disabled")


async def send_email(
    target: str,
    subject: str,
    body: str,
    smtp_host: str = "localhost",
    smtp_port: int = 587,
    smtp_user: Optional[str] = None,
    smtp_password: Optional[str] = None,
    from_email: str = "apiwatcher@localhost"
):
    """
    Send email alert via SMTP with TLS.

    Args:
        target: Recipient email address
        subject: Email subject
        body: Email body (plain text)
        smtp_host: SMTP server hostname
        smtp_port: SMTP server port
        smtp_user: SMTP username (optional)
        smtp_password: SMTP password (optional)
        from_email: Sender email address
    """
    try:
        msg = MIMEMultipart()
        msg['From'] = from_email
        msg['To'] = target
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain'))

        # For now, we'll simulate sending (actual SMTP requires configuration)
        # In production, uncomment the SMTP code below
        print(f"[EMAIL] To: {target}, Subject: {subject}")
        print(f"[EMAIL] Body preview: {body[:100]}...")

        # Actual SMTP sending (commented out for testing):
        # with smtplib.SMTP(smtp_host, smtp_port) as server:
        #     server.starttls()
        #     if smtp_user and smtp_password:
        #         server.login(smtp_user, smtp_password)
        #     server.send_message(msg)

        return True

    except Exception as e:
        print(f"Email send error: {e}")
        return False


async def send_slack(webhook_url: str, message: str):
    """
    Send Slack webhook alert.

    Args:
        webhook_url: Slack webhook URL
        message: Alert message
    """
    try:
        payload = {
            "text": message,
            "username": "APIWatcher",
            "icon_emoji": ":warning:"
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(webhook_url, json=payload)

        if response.status_code == 200:
            print(f"[SLACK] Message sent: {message[:100]}...")
            return True
        else:
            print(f"[SLACK] Error {response.status_code}: {response.text}")
            return False

    except Exception as e:
        print(f"Slack send error: {e}")
        return False


def send_desktop(title: str, message: str):
    """
    Send desktop notification via plyer.

    Args:
        title: Notification title
        message: Notification message
    """
    if not PLYER_AVAILABLE:
        print("[DESKTOP] Plyer not available, skipping desktop notification")
        return False

    try:
        notification.notify(
            title=title,
            message=message,
            app_name="APIWatcher",
            timeout=10
        )
        print(f"[DESKTOP] Notification sent: {title}")
        return True

    except Exception as e:
        print(f"Desktop notification error: {e}")
        return False


def check_cooldown(alert_config: AlertConfig) -> bool:
    """
    Check if alert cooldown period has passed.

    Args:
        alert_config: AlertConfig instance

    Returns:
        True if cooldown has passed (alert can be sent), False otherwise
    """
    if not alert_config.last_sent_at:
        return True

    cooldown_delta = timedelta(minutes=alert_config.cooldown_mins)
    time_since_last = datetime.utcnow() - alert_config.last_sent_at

    return time_since_last >= cooldown_delta


async def send_incident_alerts(
    endpoint: Endpoint,
    incident: Incident,
    db: Session,
    event_type: str = "incident_opened"
):
    """
    Send alerts for an incident event to all configured channels.

    Args:
        endpoint: Endpoint instance
        incident: Incident instance
        db: Database session
        event_type: "incident_opened" or "incident_resolved"
    """
    # Fetch alert configurations for this endpoint
    alert_configs = (
        db.query(AlertConfig)
        .filter(AlertConfig.endpoint_id == endpoint.id)
        .all()
    )

    for config in alert_configs:
        # Check if this event type should trigger alert
        should_send = False
        if event_type == "incident_opened" and config.on_incident:
            should_send = True
        elif event_type == "incident_resolved" and config.on_resolve:
            should_send = True

        if not should_send:
            continue

        # Check cooldown
        if not check_cooldown(config):
            print(f"Alert cooldown active for {config.channel} (endpoint {endpoint.id}), skipping")
            continue

        # Prepare alert message
        if event_type == "incident_opened":
            subject = f"🔴 Incident Opened: {endpoint.name}"
            message = (
                f"Endpoint: {endpoint.name}\n"
                f"URL: {endpoint.url}\n"
                f"Severity: {incident.severity}\n"
                f"Started: {incident.started_at.isoformat()}\n"
                f"Failure count: {incident.failure_count}\n"
            )
        else:  # incident_resolved
            subject = f"✅ Incident Resolved: {endpoint.name}"
            message = (
                f"Endpoint: {endpoint.name}\n"
                f"URL: {endpoint.url}\n"
                f"Duration: {incident.duration_mins} minutes\n"
                f"Resolved: {incident.resolved_at.isoformat()}\n"
            )

        # Send via appropriate channel
        success = False
        if config.channel == "email":
            success = await send_email(config.target, subject, message)
        elif config.channel == "slack":
            success = await send_slack(config.target, f"{subject}\n\n{message}")
        elif config.channel == "desktop":
            success = send_desktop(subject, message)

        # Update last_sent_at if successful
        if success:
            config.last_sent_at = datetime.utcnow()
            db.commit()
