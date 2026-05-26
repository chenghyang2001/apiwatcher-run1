"""
Async HTTP health check execution for endpoints.
"""

import json
import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
import httpx


@dataclass
class CheckResult:
    """Result of a single health check."""
    passed: bool
    status_code: Optional[int] = None
    response_time: Optional[int] = None  # milliseconds
    error_message: Optional[str] = None
    response_body: Optional[str] = None


async def run_check(endpoint) -> CheckResult:
    """
    Execute async HTTP health check for an endpoint.

    Args:
        endpoint: Endpoint ORM model instance

    Returns:
        CheckResult with check outcome and metrics
    """
    start_time = datetime.utcnow()

    try:
        # Parse headers and body from JSON strings
        headers = {}
        if endpoint.headers and endpoint.headers != "{}":
            try:
                headers = json.loads(endpoint.headers)
            except json.JSONDecodeError:
                return CheckResult(
                    passed=False,
                    error_message="Invalid JSON in headers configuration"
                )

        body = None
        if endpoint.body and endpoint.body != "{}":
            try:
                body = json.loads(endpoint.body)
            except json.JSONDecodeError:
                return CheckResult(
                    passed=False,
                    error_message="Invalid JSON in body configuration"
                )

        # Execute HTTP request with timeout
        timeout_seconds = endpoint.timeout_ms / 1000.0
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            if endpoint.method.upper() == "GET":
                response = await client.get(endpoint.url, headers=headers)
            elif endpoint.method.upper() == "POST":
                response = await client.post(endpoint.url, headers=headers, json=body)
            elif endpoint.method.upper() == "PUT":
                response = await client.put(endpoint.url, headers=headers, json=body)
            elif endpoint.method.upper() == "DELETE":
                response = await client.delete(endpoint.url, headers=headers)
            elif endpoint.method.upper() == "PATCH":
                response = await client.patch(endpoint.url, headers=headers, json=body)
            else:
                return CheckResult(
                    passed=False,
                    error_message=f"Unsupported HTTP method: {endpoint.method}"
                )

        # Calculate response time
        end_time = datetime.utcnow()
        response_time_ms = int((end_time - start_time).total_seconds() * 1000)

        # Truncate response body to 500 chars
        response_text = response.text[:500] if response.text else ""

        # Validate status code
        if response.status_code != endpoint.expected_status:
            return CheckResult(
                passed=False,
                status_code=response.status_code,
                response_time=response_time_ms,
                error_message=f"Expected status {endpoint.expected_status}, got {response.status_code}",
                response_body=response_text
            )

        # Validate response time threshold (if slow, mark as degraded but not failed)
        # For now, we consider it passed if status matches, even if slow
        # The incident.py logic can determine severity based on response time

        # Validate keyword check (optional)
        if endpoint.keyword_check:
            if endpoint.keyword_check not in response.text:
                return CheckResult(
                    passed=False,
                    status_code=response.status_code,
                    response_time=response_time_ms,
                    error_message=f"Required keyword '{endpoint.keyword_check}' not found in response",
                    response_body=response_text
                )

        # All validations passed
        return CheckResult(
            passed=True,
            status_code=response.status_code,
            response_time=response_time_ms,
            response_body=response_text
        )

    except httpx.TimeoutException:
        return CheckResult(
            passed=False,
            error_message=f"Request timeout after {endpoint.timeout_ms}ms"
        )

    except httpx.ConnectError as e:
        return CheckResult(
            passed=False,
            error_message=f"Connection error: {str(e)}"
        )

    except httpx.RequestError as e:
        return CheckResult(
            passed=False,
            error_message=f"Request error: {str(e)}"
        )

    except Exception as e:
        return CheckResult(
            passed=False,
            error_message=f"Unexpected error: {str(e)}"
        )
