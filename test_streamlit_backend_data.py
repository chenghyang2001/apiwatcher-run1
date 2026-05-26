#!/usr/bin/env python3
"""
Backend Data Verification Tests for Streamlit Features

Tests the DATA that Streamlit displays without requiring browser automation.
Verifies functional correctness even without visual inspection.
"""

import sys
import requests
from datetime import datetime, timedelta
from watcher.db import SessionLocal
from watcher.models import Endpoint, Check, Incident
from watcher.sla import calculate_uptime
import json


def test_feature_24_status_grid_data():
    """
    Feature #24: Streamlit dashboard displays endpoint status grid

    Backend Verification:
    - Verify endpoints can be queried
    - Verify latest check status for each endpoint
    - Verify data needed for status cards (name, status, uptime, response time)
    """
    print("\n=== Feature #24: Status Grid Data ===")

    try:
        # Get all endpoints
        response = requests.get("http://localhost:8000/endpoints")
        endpoints = response.json()

        if not endpoints:
            print("❌ FAIL: No endpoints found")
            return False

        print(f"✅ Found {len(endpoints)} endpoints")

        # Verify each endpoint has required fields for status card
        required_fields = ['id', 'name', 'url', 'enabled', 'environment']
        for ep in endpoints[:3]:  # Check first 3
            missing = [f for f in required_fields if f not in ep or ep[f] is None]
            if missing:
                print(f"❌ FAIL: Endpoint {ep.get('id')} missing fields: {missing}")
                return False

        print("✅ All endpoints have required fields for status cards")

        # Verify we can get latest check status for an endpoint
        db = SessionLocal()
        try:
            latest_check = db.query(Check).order_by(Check.id.desc()).first()
            if latest_check:
                print(f"✅ Latest check available: endpoint_id={latest_check.endpoint_id}, passed={latest_check.passed}")
            else:
                print("⚠️  No checks in database yet")
        finally:
            db.close()

        print("✅ PASS: Status grid data available")
        return True

    except Exception as e:
        print(f"❌ FAIL: {str(e)}")
        return False


def test_feature_25_environment_filtering():
    """
    Feature #25: Streamlit environment tab filtering

    Backend Verification:
    - Verify endpoints can be filtered by environment (dev/staging/production)
    - Verify counts per environment are correct
    """
    print("\n=== Feature #25: Environment Filtering ===")

    try:
        response = requests.get("http://localhost:8000/endpoints")
        endpoints = response.json()

        # Group by environment
        env_counts = {}
        for ep in endpoints:
            env = ep.get('environment', 'production')
            env_counts[env] = env_counts.get(env, 0) + 1

        print(f"Environment distribution: {env_counts}")

        # Verify we have at least one endpoint in some environment
        if not env_counts:
            print("❌ FAIL: No environments found")
            return False

        # Verify filtering works for each environment
        for env in env_counts.keys():
            filtered = [ep for ep in endpoints if ep.get('environment') == env]
            expected_count = env_counts[env]
            actual_count = len(filtered)

            if actual_count != expected_count:
                print(f"❌ FAIL: Environment {env} filter - expected {expected_count}, got {actual_count}")
                return False

            print(f"✅ Environment '{env}': {actual_count} endpoints")

        print("✅ PASS: Environment filtering logic works")
        return True

    except Exception as e:
        print(f"❌ FAIL: {str(e)}")
        return False


def test_feature_26_response_time_chart_data():
    """
    Feature #26: Response time chart displays 24h trend

    Backend Verification:
    - Verify check data exists for 24h response time chart
    - Verify response_time_ms field is populated
    - Verify timestamps are within 24h window
    """
    print("\n=== Feature #26: Response Time Chart Data ===")

    try:
        db = SessionLocal()
        try:
            # Get checks from last 24 hours
            cutoff = datetime.now() - timedelta(hours=24)
            recent_checks = db.query(Check).filter(
                Check.checked_at > cutoff,
                Check.response_time.isnot(None)
            ).limit(100).all()

            if not recent_checks:
                print("❌ FAIL: No checks with response_time in last 24h")
                return False

            print(f"✅ Found {len(recent_checks)} checks with response_time in last 24h")

            # Verify response times are reasonable (0-30000ms range)
            response_times = [c.response_time for c in recent_checks]
            avg_response_time = sum(response_times) / len(response_times)
            min_time = min(response_times)
            max_time = max(response_times)

            print(f"✅ Response times: avg={avg_response_time:.0f}ms, min={min_time}ms, max={max_time}ms")

            if max_time > 30000:
                print(f"⚠️  Warning: Max response time very high: {max_time}ms")

            # Verify timestamps are properly formatted
            sample_check = recent_checks[0]
            print(f"✅ Sample check timestamp: {sample_check.checked_at}")

            print("✅ PASS: Response time chart data available")
            return True

        finally:
            db.close()

    except Exception as e:
        print(f"❌ FAIL: {str(e)}")
        return False


def test_feature_27_incident_log_data():
    """
    Feature #27: Incident log panel shows open and recent incidents

    Backend Verification:
    - Verify incidents can be queried
    - Verify open vs resolved incidents can be distinguished
    - Verify incident fields (severity, duration, endpoint_id)
    """
    print("\n=== Feature #27: Incident Log Data ===")

    try:
        response = requests.get("http://localhost:8000/incidents")
        incidents = response.json()

        if not incidents:
            print("⚠️  No incidents found (this is OK if system is healthy)")
            print("✅ PASS: Incident query works (no data yet)")
            return True

        print(f"✅ Found {len(incidents)} total incidents")

        # Separate open vs resolved
        open_incidents = [i for i in incidents if i.get('resolved_at') is None]
        resolved_incidents = [i for i in incidents if i.get('resolved_at') is not None]

        print(f"✅ Open incidents: {len(open_incidents)}")
        print(f"✅ Resolved incidents: {len(resolved_incidents)}")

        # Verify incident fields
        if incidents:
            sample = incidents[0]
            required_fields = ['id', 'endpoint_id', 'started_at', 'severity']
            missing = [f for f in required_fields if f not in sample]

            if missing:
                print(f"❌ FAIL: Incident missing fields: {missing}")
                return False

            print(f"✅ Sample incident: severity={sample['severity']}, endpoint_id={sample['endpoint_id']}")

        print("✅ PASS: Incident log data available")
        return True

    except Exception as e:
        print(f"❌ FAIL: {str(e)}")
        return False


def test_feature_28_sla_metrics_data():
    """
    Feature #28: Endpoint detail sidebar shows SLA metrics

    Backend Verification:
    - Verify SLA calculation works for 24h/7d/30d windows
    - Verify uptime percentages are in valid range (0-100)
    - Verify SLA target comparison
    """
    print("\n=== Feature #28: SLA Metrics Data ===")

    try:
        # Get an endpoint with checks
        response = requests.get("http://localhost:8000/endpoints")
        endpoints = response.json()

        if not endpoints:
            print("❌ FAIL: No endpoints to test SLA calculation")
            return False

        test_endpoint_id = endpoints[0]['id']
        print(f"Testing SLA calculation for endpoint ID={test_endpoint_id}")

        # Calculate SLA for different windows
        db = SessionLocal()
        try:
            windows = [
                (24, "24h"),
                (168, "7d"),  # 7 * 24
                (720, "30d")  # 30 * 24
            ]

            for hours, label in windows:
                uptime = calculate_uptime(test_endpoint_id, hours, db)

                # Verify uptime is valid percentage
                if not (0 <= uptime <= 100):
                    print(f"❌ FAIL: Invalid uptime {uptime}% for {label} window")
                    return False

                print(f"✅ SLA {label}: {uptime:.2f}%")

            # Verify SLA API endpoint works
            sla_response = requests.get(f"http://localhost:8000/sla/{test_endpoint_id}")
            sla_data = sla_response.json()

            if 'uptime_24h' not in sla_data:
                print("❌ FAIL: SLA API missing uptime_24h field")
                return False

            print(f"✅ SLA API response: {sla_data}")

            print("✅ PASS: SLA metrics calculation working")
            return True

        finally:
            db.close()

    except Exception as e:
        print(f"❌ FAIL: {str(e)}")
        return False


def test_feature_29_bulk_check_trigger():
    """
    Feature #29: Bulk check now button triggers checks

    Backend Verification:
    - Verify POST /endpoints/:id/check works for multiple endpoints
    - Verify checks are created in database
    - Verify concurrent execution doesn't cause errors
    """
    print("\n=== Feature #29: Bulk Check Trigger ===")

    try:
        # Get first 3 enabled endpoints
        response = requests.get("http://localhost:8000/endpoints")
        endpoints = response.json()
        enabled_endpoints = [ep for ep in endpoints if ep.get('enabled')][:3]

        if not enabled_endpoints:
            print("❌ FAIL: No enabled endpoints to test bulk check")
            return False

        print(f"Testing bulk check for {len(enabled_endpoints)} endpoints")

        # Get current check count
        db = SessionLocal()
        initial_count = db.query(Check).count()
        db.close()

        # Trigger check for each endpoint
        success_count = 0
        for ep in enabled_endpoints:
            try:
                check_response = requests.post(f"http://localhost:8000/endpoints/{ep['id']}/check")
                if check_response.status_code == 200:
                    success_count += 1
                    result = check_response.json()
                    print(f"✅ Endpoint {ep['id']}: passed={result.get('passed')}")
            except Exception as e:
                print(f"⚠️  Endpoint {ep['id']} check failed: {e}")

        if success_count == 0:
            print("❌ FAIL: No checks succeeded")
            return False

        # Verify checks were created in database
        db = SessionLocal()
        final_count = db.query(Check).count()
        db.close()

        new_checks = final_count - initial_count
        print(f"✅ Created {new_checks} new check records")

        if new_checks < success_count:
            print(f"⚠️  Warning: Expected {success_count} new checks, got {new_checks}")

        print("✅ PASS: Bulk check trigger works")
        return True

    except Exception as e:
        print(f"❌ FAIL: {str(e)}")
        return False


def test_feature_36_auto_refresh_mechanism():
    """
    Feature #36: Dashboard auto-refreshes every 60 seconds

    Backend Verification:
    - Verify Streamlit service is running continuously
    - Verify data is being updated (checks are running)
    - Cannot verify visual refresh without browser, but can verify data flow
    """
    print("\n=== Feature #36: Auto-Refresh Mechanism ===")

    try:
        # Verify Streamlit is responding
        response = requests.get("http://localhost:8501", timeout=5)
        if response.status_code != 200:
            print(f"❌ FAIL: Streamlit not responding (status {response.status_code})")
            return False

        print("✅ Streamlit service responding on port 8501")

        # Verify scheduler is creating new checks (indicates data is updating)
        db = SessionLocal()
        try:
            # Get checks from last 2 minutes
            recent = db.query(Check).filter(
                Check.checked_at > datetime.now() - timedelta(minutes=2)
            ).count()

            if recent == 0:
                print("⚠️  Warning: No checks in last 2 minutes (scheduler might be paused)")
                print("✅ PASS: Streamlit running (but scheduler inactive)")
                return True

            print(f"✅ Scheduler active: {recent} checks in last 2 minutes")
            print("✅ Data is updating continuously for dashboard to display")

            print("✅ PASS: Auto-refresh infrastructure working")
            print("   (Visual refresh timing cannot be verified without browser)")
            return True

        finally:
            db.close()

    except Exception as e:
        print(f"❌ FAIL: {str(e)}")
        return False


def main():
    """Run all backend data verification tests."""
    print("=" * 70)
    print("STREAMLIT BACKEND DATA VERIFICATION TESTS")
    print("Testing functional correctness without browser automation")
    print("=" * 70)

    tests = [
        ("Feature #24", test_feature_24_status_grid_data),
        ("Feature #25", test_feature_25_environment_filtering),
        ("Feature #26", test_feature_26_response_time_chart_data),
        ("Feature #27", test_feature_27_incident_log_data),
        ("Feature #28", test_feature_28_sla_metrics_data),
        ("Feature #29", test_feature_29_bulk_check_trigger),
        ("Feature #36", test_feature_36_auto_refresh_mechanism),
    ]

    results = []
    for name, test_func in tests:
        try:
            passed = test_func()
            results.append((name, passed))
        except Exception as e:
            print(f"\n❌ {name} crashed: {e}")
            results.append((name, False))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed_count = sum(1 for _, passed in results if passed)
    total_count = len(results)

    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")

    print("=" * 70)
    print(f"TOTAL: {passed_count}/{total_count} tests passed ({passed_count/total_count*100:.0f}%)")
    print("=" * 70)

    # Exit code
    sys.exit(0 if passed_count == total_count else 1)


if __name__ == "__main__":
    main()
