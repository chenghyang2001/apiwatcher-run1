"""
SQLAlchemy ORM models for APIWatcher database schema.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Float, DateTime, ForeignKey
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Endpoint(Base):
    """
    Monitored API endpoint configuration.
    """
    __tablename__ = "endpoints"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    url = Column(Text, nullable=False)
    method = Column(String(10), nullable=False, default="GET")
    headers = Column(Text, default="{}")  # JSON string
    body = Column(Text, default="{}")  # JSON string
    environment = Column(String(50), default="production")
    check_interval = Column(Integer, default=300)  # seconds
    timeout_ms = Column(Integer, default=5000)
    expected_status = Column(Integer, default=200)
    keyword_check = Column(String(255), nullable=True)  # optional keyword in response
    sla_target = Column(Float, default=99.9)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    checks = relationship("Check", back_populates="endpoint", cascade="all, delete-orphan")
    incidents = relationship("Incident", back_populates="endpoint", cascade="all, delete-orphan")
    alert_configs = relationship("AlertConfig", back_populates="endpoint", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Endpoint(id={self.id}, name='{self.name}', url='{self.url}', enabled={self.enabled})>"


class Check(Base):
    """
    Individual health check result for an endpoint.
    """
    __tablename__ = "checks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    endpoint_id = Column(Integer, ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False)
    checked_at = Column(DateTime, default=datetime.utcnow)
    passed = Column(Boolean, nullable=False)
    status_code = Column(Integer, nullable=True)
    response_time = Column(Integer, nullable=True)  # milliseconds
    error_message = Column(Text, nullable=True)
    response_body = Column(Text, nullable=True)  # truncated to 500 chars

    # Relationship
    endpoint = relationship("Endpoint", back_populates="checks")

    def __repr__(self):
        return f"<Check(id={self.id}, endpoint_id={self.endpoint_id}, passed={self.passed}, checked_at={self.checked_at})>"


class Incident(Base):
    """
    Endpoint failure incident tracking.
    """
    __tablename__ = "incidents"

    id = Column(Integer, primary_key=True, autoincrement=True)
    endpoint_id = Column(Integer, ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=False)
    started_at = Column(DateTime, default=datetime.utcnow)
    resolved_at = Column(DateTime, nullable=True)
    duration_mins = Column(Integer, nullable=True)
    failure_count = Column(Integer, default=1)
    severity = Column(String(10), default="MEDIUM")  # LOW | MEDIUM | HIGH
    claude_report = Column(Text, nullable=True)
    acknowledged = Column(Boolean, default=False)

    # Relationship
    endpoint = relationship("Endpoint", back_populates="incidents")

    def __repr__(self):
        status = "open" if self.resolved_at is None else "resolved"
        return f"<Incident(id={self.id}, endpoint_id={self.endpoint_id}, severity='{self.severity}', status='{status}')>"


class AlertConfig(Base):
    """
    Per-endpoint alert channel configuration.
    """
    __tablename__ = "alert_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    endpoint_id = Column(Integer, ForeignKey("endpoints.id", ondelete="CASCADE"), nullable=True)
    channel = Column(String(20), nullable=False)  # email | slack | desktop
    target = Column(String(255), nullable=False)  # email address or webhook URL
    on_incident = Column(Boolean, default=True)
    on_resolve = Column(Boolean, default=True)
    on_sla_breach = Column(Boolean, default=True)
    cooldown_mins = Column(Integer, default=15)
    last_sent_at = Column(DateTime, nullable=True)

    # Relationship
    endpoint = relationship("Endpoint", back_populates="alert_configs")

    def __repr__(self):
        return f"<AlertConfig(id={self.id}, endpoint_id={self.endpoint_id}, channel='{self.channel}', target='{self.target}')>"
