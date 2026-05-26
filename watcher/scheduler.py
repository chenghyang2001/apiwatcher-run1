"""
APScheduler setup and job management for periodic health checks.
"""

import asyncio
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from .db import get_db
from .models import Endpoint, Check
from .checker import run_check
from .incident import evaluate_incident

# Global scheduler instance
scheduler = AsyncIOScheduler()


async def execute_check_job(endpoint_id: int):
    """
    Job function executed by APScheduler for each endpoint check.

    Args:
        endpoint_id: ID of the endpoint to check
    """
    print(f"[{datetime.utcnow().isoformat()}] Running check for endpoint_id={endpoint_id}")

    with get_db() as db:
        # Fetch endpoint
        endpoint = db.query(Endpoint).filter(Endpoint.id == endpoint_id).first()
        if not endpoint:
            print(f"Endpoint {endpoint_id} not found, removing job")
            remove_job(endpoint_id)
            return

        if not endpoint.enabled:
            print(f"Endpoint {endpoint_id} is disabled, skipping check")
            return

        # Run async check
        result = await run_check(endpoint)

        # Save check result to database
        check = Check(
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

        print(f"Check saved: endpoint_id={endpoint_id}, passed={result.passed}, "
              f"status_code={result.status_code}, response_time={result.response_time}ms")

        # Evaluate incident detection logic
        await evaluate_incident(endpoint_id, db)


def add_job(endpoint_id: int, interval_seconds: int):
    """
    Add or update a scheduled job for an endpoint.

    Args:
        endpoint_id: ID of the endpoint
        interval_seconds: Check interval in seconds
    """
    job_id = f"endpoint_{endpoint_id}"

    # Remove existing job if present
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)

    # Add new job with interval trigger
    scheduler.add_job(
        execute_check_job,
        trigger=IntervalTrigger(seconds=interval_seconds),
        args=[endpoint_id],
        id=job_id,
        name=f"Check endpoint {endpoint_id}",
        replace_existing=True
    )
    print(f"Added job for endpoint {endpoint_id} with interval {interval_seconds}s")


def remove_job(endpoint_id: int):
    """
    Remove a scheduled job for an endpoint.

    Args:
        endpoint_id: ID of the endpoint
    """
    job_id = f"endpoint_{endpoint_id}"
    if scheduler.get_job(job_id):
        scheduler.remove_job(job_id)
        print(f"Removed job for endpoint {endpoint_id}")


def update_job(endpoint_id: int, interval_seconds: int):
    """
    Update the interval for an existing job.

    Args:
        endpoint_id: ID of the endpoint
        interval_seconds: New check interval in seconds
    """
    add_job(endpoint_id, interval_seconds)  # add_job replaces existing


def load_all_jobs():
    """
    Load all enabled endpoints from database and schedule their jobs.
    Called on application startup.
    """
    with get_db() as db:
        endpoints = db.query(Endpoint).filter(Endpoint.enabled == True).all()
        for endpoint in endpoints:
            add_job(endpoint.id, endpoint.check_interval)
        print(f"Loaded {len(endpoints)} endpoint jobs into scheduler")


def start_scheduler():
    """
    Start the APScheduler.
    Should be called once on application startup.
    """
    if not scheduler.running:
        scheduler.start()
        print("✓ APScheduler started")
        load_all_jobs()


def shutdown_scheduler():
    """
    Shutdown the APScheduler.
    Should be called on application shutdown.
    """
    if scheduler.running:
        scheduler.shutdown()
        print("✓ APScheduler shutdown")
