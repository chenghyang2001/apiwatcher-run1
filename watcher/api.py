"""
FastAPI REST API application for APIWatcher.
"""

import json
import yaml
from contextlib import asynccontextmanager
from typing import List, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, Depends, Body
from fastapi.responses import PlainTextResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .db import init_db, get_db_session
from .models import Endpoint, Check, Incident, AlertConfig
from .scheduler import start_scheduler, shutdown_scheduler, add_job, remove_job, update_job
from .checker import run_check
from .sla import calculate_uptime, export_sla_csv
from .claude_reporter import reanalyze_incident
from .models import Check as CheckModel
from .pdf_export import generate_incident_pdf


# Pydantic schemas for request/response
class EndpointCreate(BaseModel):
    name: str
    url: str
    method: str = "GET"
    headers: str = "{}"
    body: str = "{}"
    environment: str = "production"
    check_interval: int = 300
    timeout_ms: int = 5000
    expected_status: int = 200
    keyword_check: Optional[str] = None
    sla_target: float = 99.9
    enabled: bool = True


class EndpointUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    method: Optional[str] = None
    headers: Optional[str] = None
    body: Optional[str] = None
    environment: Optional[str] = None
    check_interval: Optional[int] = None
    timeout_ms: Optional[int] = None
    expected_status: Optional[int] = None
    keyword_check: Optional[str] = None
    sla_target: Optional[float] = None
    enabled: Optional[bool] = None


class AlertConfigUpdate(BaseModel):
    channel: str
    target: str
    on_incident: bool = True
    on_resolve: bool = True
    on_sla_breach: bool = True
    cooldown_mins: int = 15


# Application lifespan context manager
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan: startup and shutdown events.
    """
    # Startup
    print("=== APIWatcher FastAPI Starting ===")
    init_db()
    start_scheduler()
    yield
    # Shutdown
    print("=== APIWatcher FastAPI Shutting Down ===")
    shutdown_scheduler()


# Create FastAPI app
app = FastAPI(
    title="APIWatcher",
    description="REST API Endpoint Monitor",
    version="0.1.0",
    lifespan=lifespan
)


# Health check endpoint
@app.get("/health")
async def health_check():
    """Service health check."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "APIWatcher"
    }


# ===== ENDPOINTS CRUD =====

@app.get("/endpoints")
async def list_endpoints(db: Session = Depends(get_db_session)):
    """List all configured endpoints."""
    try:
        endpoints = db.query(Endpoint).all()
        return [
            {
                "id": e.id,
                "name": e.name,
                "url": e.url,
                "method": e.method,
                "environment": e.environment,
                "check_interval": e.check_interval,
                "enabled": e.enabled,
                "created_at": e.created_at.isoformat()
            }
            for e in endpoints
        ]
    finally:
        db.close()


@app.post("/endpoints", status_code=201)
async def create_endpoint(endpoint: EndpointCreate, db: Session = Depends(get_db_session)):
    """Create a new endpoint."""
    try:
        new_endpoint = Endpoint(**endpoint.dict())
        db.add(new_endpoint)
        db.commit()
        db.refresh(new_endpoint)

        # Schedule the check job
        if new_endpoint.enabled:
            add_job(new_endpoint.id, new_endpoint.check_interval)

        return {
            "id": new_endpoint.id,
            "name": new_endpoint.name,
            "url": new_endpoint.url,
            "enabled": new_endpoint.enabled,
            "message": "Endpoint created successfully"
        }
    finally:
        db.close()


@app.get("/endpoints/export", response_class=PlainTextResponse)
async def export_endpoints_yaml(db: Session = Depends(get_db_session)):
    """Export all endpoints as YAML."""
    try:
        endpoints = db.query(Endpoint).all()
        export_data = []

        for e in endpoints:
            export_data.append({
                "name": e.name,
                "url": e.url,
                "method": e.method,
                "headers": e.headers,
                "body": e.body,
                "environment": e.environment,
                "check_interval": e.check_interval,
                "timeout_ms": e.timeout_ms,
                "expected_status": e.expected_status,
                "keyword_check": e.keyword_check,
                "sla_target": e.sla_target,
                "enabled": e.enabled
            })

        return yaml.dump(export_data, default_flow_style=False)
    finally:
        db.close()


@app.post("/endpoints/import")
async def import_endpoints_yaml(yaml_content: str = Body(..., media_type="text/plain"), db: Session = Depends(get_db_session)):
    """Import endpoints from YAML."""
    try:
        data = yaml.safe_load(yaml_content)
        if not isinstance(data, list):
            raise HTTPException(status_code=400, detail="YAML must be a list of endpoints")

        imported_count = 0
        for item in data:
            endpoint = Endpoint(**item)
            db.add(endpoint)
            imported_count += 1

        db.commit()

        return {"message": f"Imported {imported_count} endpoints"}
    except yaml.YAMLError as e:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {str(e)}")
    finally:
        db.close()


@app.get("/endpoints/{endpoint_id}")
async def get_endpoint(endpoint_id: int, db: Session = Depends(get_db_session)):
    """Get endpoint details."""
    try:
        endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
        if not endpoint:
            raise HTTPException(status_code=404, detail="Endpoint not found")

        return {
            "id": endpoint.id,
            "name": endpoint.name,
            "url": endpoint.url,
            "method": endpoint.method,
            "headers": endpoint.headers,
            "body": endpoint.body,
            "environment": endpoint.environment,
            "check_interval": endpoint.check_interval,
            "timeout_ms": endpoint.timeout_ms,
            "expected_status": endpoint.expected_status,
            "keyword_check": endpoint.keyword_check,
            "sla_target": endpoint.sla_target,
            "enabled": endpoint.enabled,
            "created_at": endpoint.created_at.isoformat()
        }
    finally:
        db.close()


@app.put("/endpoints/{endpoint_id}")
async def update_endpoint(endpoint_id: int, updates: EndpointUpdate, db: Session = Depends(get_db_session)):
    """Update endpoint configuration."""
    try:
        endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
        if not endpoint:
            raise HTTPException(status_code=404, detail="Endpoint not found")

        update_data = updates.dict(exclude_unset=True)
        for key, value in update_data.items():
            setattr(endpoint, key, value)

        db.commit()

        # Update scheduler job if interval changed
        if "check_interval" in update_data and endpoint.enabled:
            update_job(endpoint_id, endpoint.check_interval)

        return {"message": "Endpoint updated successfully"}
    finally:
        db.close()


@app.delete("/endpoints/{endpoint_id}")
async def delete_endpoint(endpoint_id: int, db: Session = Depends(get_db_session)):
    """Delete an endpoint."""
    try:
        endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
        if not endpoint:
            raise HTTPException(status_code=404, detail="Endpoint not found")

        # Remove scheduler job
        remove_job(endpoint_id)

        # Delete from database (cascades to checks, incidents, alert_configs)
        db.delete(endpoint)
        db.commit()

        return {"message": "Endpoint deleted successfully"}
    finally:
        db.close()


@app.post("/endpoints/{endpoint_id}/check")
async def trigger_manual_check(endpoint_id: int, db: Session = Depends(get_db_session)):
    """Trigger immediate manual check for an endpoint."""
    try:
        endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
        if not endpoint:
            raise HTTPException(status_code=404, detail="Endpoint not found")

        # Run check
        result = await run_check(endpoint)

        # Save result
        check = CheckModel(
            endpoint_id=endpoint_id,
            passed=result.passed,
            status_code=result.status_code,
            response_time=result.response_time,
            error_message=result.error_message,
            response_body=result.response_body,
            checked_at=datetime.utcnow()
        )
        db.add(check)
        db.commit()
        db.refresh(check)

        # Evaluate incident detection logic
        from .incident import evaluate_incident
        await evaluate_incident(endpoint_id, db)

        return {
            "check_id": check.id,
            "passed": check.passed,
            "status_code": check.status_code,
            "response_time": check.response_time,
            "error_message": check.error_message,
            "checked_at": check.checked_at.isoformat()
        }
    finally:
        db.close()


@app.put("/endpoints/{endpoint_id}/toggle")
async def toggle_endpoint(endpoint_id: int, db: Session = Depends(get_db_session)):
    """Enable or disable an endpoint."""
    try:
        endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
        if not endpoint:
            raise HTTPException(status_code=404, detail="Endpoint not found")

        # Toggle enabled status
        endpoint.enabled = not endpoint.enabled
        db.commit()

        # Update scheduler
        if endpoint.enabled:
            add_job(endpoint_id, endpoint.check_interval)
        else:
            remove_job(endpoint_id)

        return {
            "endpoint_id": endpoint_id,
            "enabled": endpoint.enabled,
            "message": f"Endpoint {'enabled' if endpoint.enabled else 'disabled'}"
        }
    finally:
        db.close()


# ===== CHECKS =====

@app.get("/checks/{endpoint_id}")
async def get_check_history(
    endpoint_id: int,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db_session)
):
    """Get check history for an endpoint (paginated)."""
    try:
        checks = (
            db.query(CheckModel)
            .filter(CheckModel.endpoint_id == endpoint_id)
            .order_by(CheckModel.id.desc())
            .limit(limit)
            .offset(offset)
            .all()
        )

        return [
            {
                "id": c.id,
                "checked_at": c.checked_at.isoformat(),
                "passed": c.passed,
                "status_code": c.status_code,
                "response_time": c.response_time,
                "error_message": c.error_message
            }
            for c in checks
        ]
    finally:
        db.close()


@app.get("/checks/{endpoint_id}/latest")
async def get_latest_check(endpoint_id: int, db: Session = Depends(get_db_session)):
    """Get most recent check result for an endpoint."""
    try:
        check = (
            db.query(CheckModel)
            .filter(CheckModel.endpoint_id == endpoint_id)
            .order_by(CheckModel.id.desc())
            .first()
        )

        if not check:
            raise HTTPException(status_code=404, detail="No checks found for this endpoint")

        return {
            "id": check.id,
            "checked_at": check.checked_at.isoformat(),
            "passed": check.passed,
            "status_code": check.status_code,
            "response_time": check.response_time,
            "error_message": check.error_message
        }
    finally:
        db.close()


# ===== INCIDENTS =====

@app.get("/incidents")
async def list_incidents(status: Optional[str] = None, db: Session = Depends(get_db_session)):
    """List all incidents (filter: open/resolved)."""
    try:
        query = db.query(Incident)

        if status == "open":
            query = query.filter(Incident.resolved_at == None)
        elif status == "resolved":
            query = query.filter(Incident.resolved_at != None)

        incidents = query.order_by(Incident.id.desc()).all()

        return [
            {
                "id": i.id,
                "endpoint_id": i.endpoint_id,
                "started_at": i.started_at.isoformat(),
                "resolved_at": i.resolved_at.isoformat() if i.resolved_at else None,
                "duration_mins": i.duration_mins,
                "severity": i.severity,
                "acknowledged": i.acknowledged
            }
            for i in incidents
        ]
    finally:
        db.close()


@app.get("/incidents/{incident_id}")
async def get_incident_detail(incident_id: int, db: Session = Depends(get_db_session)):
    """Get incident details with Claude report."""
    try:
        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        return {
            "id": incident.id,
            "endpoint_id": incident.endpoint_id,
            "started_at": incident.started_at.isoformat(),
            "resolved_at": incident.resolved_at.isoformat() if incident.resolved_at else None,
            "duration_mins": incident.duration_mins,
            "failure_count": incident.failure_count,
            "severity": incident.severity,
            "claude_report": incident.claude_report,
            "acknowledged": incident.acknowledged
        }
    finally:
        db.close()


@app.put("/incidents/{incident_id}/acknowledge")
async def acknowledge_incident(incident_id: int, db: Session = Depends(get_db_session)):
    """Mark incident as acknowledged."""
    try:
        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        incident.acknowledged = True
        db.commit()

        return {
            "incident_id": incident_id,
            "acknowledged": True,
            "timestamp": datetime.utcnow().isoformat()
        }
    finally:
        db.close()


@app.post("/incidents/{incident_id}/reanalyze")
async def reanalyze_incident_endpoint(incident_id: int, db: Session = Depends(get_db_session)):
    """Regenerate Claude AI analysis for an incident."""
    try:
        success = await reanalyze_incident(incident_id, db)
        if not success:
            raise HTTPException(status_code=404, detail="Incident not found or reanalysis failed")

        return {"message": "Incident reanalyzed successfully"}
    finally:
        db.close()


@app.get("/incidents/{incident_id}/export/pdf")
async def export_incident_pdf(incident_id: int, db: Session = Depends(get_db_session)):
    """Export incident report as PDF."""
    try:
        # Verify incident exists
        incident = db.query(Incident).filter(Incident.id == incident_id).first()
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        # Get endpoint for filename
        endpoint = db.query(Endpoint).filter(Endpoint.id == incident.endpoint_id).first()
        endpoint_name = endpoint.name.replace(" ", "_").replace("/", "_") if endpoint else "unknown"

        # Generate PDF
        pdf_bytes = generate_incident_pdf(incident_id, db)

        # Return PDF response
        filename = f"incident_{incident_id}_{endpoint_name}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.pdf"

        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename={filename}"
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    finally:
        db.close()


# ===== SLA =====

@app.get("/sla/{endpoint_id}")
async def get_sla_metrics(endpoint_id: int, db: Session = Depends(get_db_session)):
    """Get SLA uptime metrics for 24h/7d/30d windows."""
    try:
        uptime_24h = calculate_uptime(endpoint_id, 24, db)
        uptime_7d = calculate_uptime(endpoint_id, 168, db)
        uptime_30d = calculate_uptime(endpoint_id, 720, db)

        return {
            "endpoint_id": endpoint_id,
            "uptime_24h": uptime_24h,
            "uptime_7d": uptime_7d,
            "uptime_30d": uptime_30d,
            "timestamp": datetime.utcnow().isoformat()
        }
    finally:
        db.close()


@app.get("/sla/{endpoint_id}/export", response_class=PlainTextResponse)
async def export_sla_history(endpoint_id: int, db: Session = Depends(get_db_session)):
    """Export SLA history as CSV."""
    try:
        csv_content = export_sla_csv(endpoint_id, db)
        return csv_content
    finally:
        db.close()


# ===== ALERTS =====

@app.get("/alert-configs/{endpoint_id}")
async def get_alert_configs(endpoint_id: int, db: Session = Depends(get_db_session)):
    """Get alert configurations for an endpoint."""
    try:
        configs = db.query(AlertConfig).filter(AlertConfig.endpoint_id == endpoint_id).all()
        return [
            {
                "id": c.id,
                "channel": c.channel,
                "target": c.target,
                "on_incident": c.on_incident,
                "on_resolve": c.on_resolve,
                "on_sla_breach": c.on_sla_breach,
                "cooldown_mins": c.cooldown_mins
            }
            for c in configs
        ]
    finally:
        db.close()


@app.put("/alert-configs/{endpoint_id}")
async def update_alert_config(
    endpoint_id: int,
    config: AlertConfigUpdate,
    db: Session = Depends(get_db_session)
):
    """Update or create alert configuration for an endpoint."""
    try:
        # Find existing config for this channel
        existing = (
            db.query(AlertConfig)
            .filter(
                AlertConfig.endpoint_id == endpoint_id,
                AlertConfig.channel == config.channel
            )
            .first()
        )

        if existing:
            # Update existing
            existing.target = config.target
            existing.on_incident = config.on_incident
            existing.on_resolve = config.on_resolve
            existing.on_sla_breach = config.on_sla_breach
            existing.cooldown_mins = config.cooldown_mins
        else:
            # Create new
            new_config = AlertConfig(
                endpoint_id=endpoint_id,
                **config.dict()
            )
            db.add(new_config)

        db.commit()

        return {"message": "Alert configuration updated successfully"}
    finally:
        db.close()
