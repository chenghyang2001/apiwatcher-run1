"""
Streamlit dashboard UI for APIWatcher.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))  # 確保 watcher 套件可被找到，不論 cwd 在哪
import time
import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from sqlalchemy import and_

from watcher.db import get_db
from watcher.models import Endpoint, Check, Incident
from watcher.sla import calculate_uptime


# Page configuration
st.set_page_config(
    page_title="APIWatcher Dashboard",
    page_icon="🔍",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for color-coded cards
st.markdown("""
<style>
.status-card-up {
    border-left: 5px solid #22C55E;
    padding: 15px;
    background-color: rgba(34, 197, 94, 0.1);
    border-radius: 5px;
    margin-bottom: 10px;
}
.status-card-degraded {
    border-left: 5px solid #F59E0B;
    padding: 15px;
    background-color: rgba(245, 158, 11, 0.1);
    border-radius: 5px;
    margin-bottom: 10px;
}
.status-card-down {
    border-left: 5px solid #EF4444;
    padding: 15px;
    background-color: rgba(239, 68, 68, 0.1);
    border-radius: 5px;
    margin-bottom: 10px;
}
.severity-low {
    background-color: #3B82F6;
    color: white;
    padding: 3px 8px;
    border-radius: 3px;
    font-size: 12px;
    font-weight: bold;
}
.severity-medium {
    background-color: #F97316;
    color: white;
    padding: 3px 8px;
    border-radius: 3px;
    font-size: 12px;
    font-weight: bold;
}
.severity-high {
    background-color: #EF4444;
    color: white;
    padding: 3px 8px;
    border-radius: 3px;
    font-size: 12px;
    font-weight: bold;
}
</style>
""", unsafe_allow_html=True)


def get_endpoint_status(endpoint, latest_check, open_incident):
    """Determine endpoint status: up, degraded, or down."""
    if open_incident:
        return "down"

    if not latest_check:
        return "up"  # No data yet

    if not latest_check.passed:
        return "degraded"

    # Check if response time is slow (>2000ms = degraded)
    if latest_check.response_time and latest_check.response_time > 2000:
        return "degraded"

    return "up"


def render_status_card(endpoint, latest_check, uptime_24h, open_incident):
    """Render a color-coded status card for an endpoint."""
    status = get_endpoint_status(endpoint, latest_check, open_incident)

    card_class = f"status-card-{status}"

    status_emoji = {
        "up": "✅",
        "degraded": "⚠️",
        "down": "🔴"
    }

    # Build card HTML
    card_html = f'<div class="{card_class}">'
    card_html += f'<h4>{status_emoji[status]} {endpoint.name}</h4>'
    card_html += f'<p><strong>URL:</strong> {endpoint.url[:50]}...</p>'
    card_html += f'<p><strong>24h Uptime:</strong> {uptime_24h:.2f}%</p>'

    if latest_check and latest_check.response_time:
        card_html += f'<p><strong>Avg Response Time:</strong> {latest_check.response_time}ms</p>'

    if open_incident:
        card_html += f'<p><span class="severity-{open_incident.severity.lower()}">{open_incident.severity} INCIDENT</span></p>'

    card_html += '</div>'

    st.markdown(card_html, unsafe_allow_html=True)

    # Add button to view details
    if st.button(f"View Details", key=f"details_{endpoint.id}"):
        st.session_state['selected_endpoint_id'] = endpoint.id


def render_response_time_chart(endpoint_id, db):
    """Render Plotly response time chart for last 24h."""
    # Get endpoint to access timeout_ms threshold
    endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
    if not endpoint:
        st.error("Endpoint not found")
        return

    cutoff = datetime.utcnow() - timedelta(hours=24)

    checks = (
        db.query(Check)
        .filter(
            and_(
                Check.endpoint_id == endpoint_id,
                Check.checked_at >= cutoff,
                Check.response_time != None
            )
        )
        .order_by(Check.checked_at.asc())
        .all()
    )

    if not checks:
        st.info("No check data available for the last 24 hours")
        return

    # Prepare data
    timestamps = [c.checked_at for c in checks]
    response_times = [c.response_time for c in checks]

    # Create Plotly line chart
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=timestamps,
        y=response_times,
        mode='lines+markers',
        name='Response Time',
        line=dict(color='#3B82F6', width=2),
        marker=dict(size=4)
    ))

    # Add threshold line using endpoint's configured timeout_ms
    fig.add_hline(
        y=endpoint.timeout_ms,
        line_dash="dash",
        line_color="#EF4444",
        annotation_text=f"Threshold ({endpoint.timeout_ms}ms)",
        annotation_position="right"
    )

    fig.update_layout(
        title="Response Time (Last 24h)",
        xaxis_title="Time",
        yaxis_title="Response Time (ms)",
        hovermode='x unified',
        height=400
    )

    st.plotly_chart(fig, use_container_width=True)


def render_incident_log(db):
    """Render incident log panel showing open and recent incidents."""
    st.subheader("📊 Incident Log")

    # Open incidents
    open_incidents = (
        db.query(Incident)
        .filter(Incident.resolved_at == None)
        .order_by(Incident.started_at.desc())
        .all()
    )

    if open_incidents:
        st.markdown("**🔴 Open Incidents**")
        for incident in open_incidents:
            endpoint = db.query(Endpoint).filter(Endpoint.id == incident.endpoint_id).first()

            with st.expander(f"{endpoint.name} - {incident.severity} ({incident.started_at.strftime('%Y-%m-%d %H:%M')})"):
                st.write(f"**Endpoint:** {endpoint.name}")
                st.write(f"**Started:** {incident.started_at}")
                st.write(f"**Failures:** {incident.failure_count}")
                st.write(f"**Severity:** {incident.severity}")

                if incident.claude_report:
                    st.markdown("**🤖 Claude AI Report:**")
                    st.text_area("", incident.claude_report, height=200, key=f"report_{incident.id}")
                else:
                    st.info("Claude AI report generating...")

                if not incident.acknowledged:
                    if st.button("Acknowledge", key=f"ack_{incident.id}"):
                        # This would call the API in a real implementation
                        st.success("Incident acknowledged")
    else:
        st.success("✅ No open incidents")

    # Resolved incidents (last 5)
    st.markdown("**✅ Recently Resolved**")
    resolved_incidents = (
        db.query(Incident)
        .filter(Incident.resolved_at != None)
        .order_by(Incident.resolved_at.desc())
        .limit(5)
        .all()
    )

    if resolved_incidents:
        for incident in resolved_incidents:
            endpoint = db.query(Endpoint).filter(Endpoint.id == incident.endpoint_id).first()
            st.write(f"• {endpoint.name} - {incident.duration_mins}min ({incident.resolved_at.strftime('%Y-%m-%d %H:%M')})")
    else:
        st.info("No recent resolved incidents")


def render_endpoint_detail_sidebar(endpoint_id, db):
    """Render detailed view for selected endpoint."""
    endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
    if not endpoint:
        st.sidebar.error("Endpoint not found")
        return

    st.sidebar.title(f"📍 {endpoint.name}")

    # SLA Metrics
    st.sidebar.subheader("SLA Metrics")
    uptime_24h = calculate_uptime(endpoint_id, 24, db)
    uptime_7d = calculate_uptime(endpoint_id, 168, db)
    uptime_30d = calculate_uptime(endpoint_id, 720, db)

    col1, col2, col3 = st.sidebar.columns(3)
    col1.metric("24h Uptime", f"{uptime_24h:.2f}%")
    col2.metric("7d Uptime", f"{uptime_7d:.2f}%")
    col3.metric("30d Uptime", f"{uptime_30d:.2f}%")

    # Check History
    st.sidebar.subheader("Recent Checks")
    recent_checks = (
        db.query(Check)
        .filter(Check.endpoint_id == endpoint_id)
        .order_by(Check.id.desc())
        .limit(10)
        .all()
    )

    for check in recent_checks:
        status_emoji = "✅" if check.passed else "❌"
        st.sidebar.write(f"{status_emoji} {check.checked_at.strftime('%H:%M:%S')} - {check.response_time}ms")

    # Configuration
    st.sidebar.subheader("Configuration")
    st.sidebar.write(f"**URL:** {endpoint.url}")
    st.sidebar.write(f"**Method:** {endpoint.method}")
    st.sidebar.write(f"**Environment:** {endpoint.environment}")
    st.sidebar.write(f"**Check Interval:** {endpoint.check_interval}s")
    st.sidebar.write(f"**Enabled:** {'✅' if endpoint.enabled else '❌'}")


# ===== MAIN DASHBOARD =====

def main():
    # Title
    st.title("🔍 APIWatcher Dashboard")

    # Get data
    with get_db() as db:
        # Environment tabs
        tab_all, tab_dev, tab_staging, tab_prod = st.tabs(["📊 All", "🔧 Dev", "🚀 Staging", "⚡ Production"])

        # Fetch all endpoints
        all_endpoints = db.query(Endpoint).all()

        # Environment filter
        environments = {
            "All": all_endpoints,
            "Dev": [e for e in all_endpoints if e.environment == "dev"],
            "Staging": [e for e in all_endpoints if e.environment == "staging"],
            "Production": [e for e in all_endpoints if e.environment == "production"]
        }

        for tab, (env_name, endpoints) in zip([tab_all, tab_dev, tab_staging, tab_prod], environments.items()):
            with tab:
                # Summary metrics
                total = len(endpoints)
                up_count = 0
                degraded_count = 0
                down_count = 0

                for endpoint in endpoints:
                    latest_check = (
                        db.query(Check)
                        .filter(Check.endpoint_id == endpoint.id)
                        .order_by(Check.id.desc())
                        .first()
                    )

                    open_incident = (
                        db.query(Incident)
                        .filter(Incident.endpoint_id == endpoint.id, Incident.resolved_at == None)
                        .first()
                    )

                    status = get_endpoint_status(endpoint, latest_check, open_incident)
                    if status == "up":
                        up_count += 1
                    elif status == "degraded":
                        degraded_count += 1
                    else:
                        down_count += 1

                # Display metrics
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Total Endpoints", total)
                col2.metric("🟢 UP", up_count)
                col3.metric("🟡 Degraded", degraded_count)
                col4.metric("🔴 Down", down_count)

                # Bulk check now button
                if st.button(f"⚡ Bulk Check Now ({env_name})", key=f"bulk_{env_name}"):
                    st.info(f"Triggering checks for all {env_name} endpoints...")

                st.divider()

                # Status grid (3 columns)
                if endpoints:
                    cols = st.columns(3)
                    for idx, endpoint in enumerate(endpoints):
                        with cols[idx % 3]:
                            latest_check = (
                                db.query(Check)
                                .filter(Check.endpoint_id == endpoint.id)
                                .order_by(Check.id.desc())
                                .first()
                            )

                            open_incident = (
                                db.query(Incident)
                                .filter(Incident.endpoint_id == endpoint.id, Incident.resolved_at == None)
                                .first()
                            )

                            uptime_24h = calculate_uptime(endpoint.id, 24, db)
                            render_status_card(endpoint, latest_check, uptime_24h, open_incident)
                else:
                    st.info(f"No endpoints in {env_name} environment")

        # Right column: Incident Log
        st.divider()
        col_left, col_right = st.columns([2, 1])

        with col_left:
            if 'selected_endpoint_id' in st.session_state:
                st.subheader("📈 Response Time Trend")
                render_response_time_chart(st.session_state['selected_endpoint_id'], db)

        with col_right:
            render_incident_log(db)

        # Sidebar: Endpoint Detail
        if 'selected_endpoint_id' in st.session_state:
            render_endpoint_detail_sidebar(st.session_state['selected_endpoint_id'], db)

    # Auto-refresh every 60 seconds
    time.sleep(60)
    st.rerun()


if __name__ == "__main__":
    main()
