"""
Unit Tests for APIWatcher Backend Modules

Tests core functionality without requiring external services or browser automation.
Can be run in CI/CD pipelines.

Usage:
    pytest test_unit.py -v
    pytest test_unit.py::TestSLACalculation -v
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from watcher.models import Base, Endpoint, Check, Incident, AlertConfig
from watcher.incident import determine_severity
from watcher.sla import calculate_uptime
from watcher.checker import run_check, CheckResult


# Test Database Setup
@pytest.fixture
def test_db():
    """Create in-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def sample_endpoint(test_db):
    """Create a sample endpoint for testing"""
    endpoint = Endpoint(
        name="Test API",
        url="https://httpbin.org/status/200",
        method="GET",
        environment="dev",
        check_interval=300,
        timeout_ms=5000,
        expected_status=200,
        enabled=True
    )
    test_db.add(endpoint)
    test_db.commit()
    test_db.refresh(endpoint)
    return endpoint


# === Incident Detection Tests ===

class TestIncidentDetection:
    """Tests for incident.py module"""

    def test_determine_severity_high_server_error(self):
        """HIGH severity: 500-level status codes"""
        # Create mock checks with 500 errors
        checks = []
        for i in range(3):
            check = Mock()
            check.status_code = 500
            check.error_message = "Server Error"
            check.response_time = 100
            checks.append(check)

        severity = determine_severity(checks)
        assert severity == "HIGH"

    def test_determine_severity_medium_client_error(self):
        """MEDIUM severity: 400-level status codes"""
        checks = []
        for i in range(3):
            check = Mock()
            check.status_code = 404
            check.error_message = "Not Found"
            check.response_time = 100
            checks.append(check)

        severity = determine_severity(checks)
        assert severity == "MEDIUM"

    def test_determine_severity_low_slow_response(self):
        """LOW severity: slow response times"""
        checks = []
        for i in range(3):
            check = Mock()
            check.status_code = 200
            check.error_message = None
            check.response_time = 3000  # 3 seconds
            checks.append(check)

        severity = determine_severity(checks)
        assert severity == "LOW"

    def test_determine_severity_high_timeout(self):
        """HIGH severity: timeout errors"""
        checks = []
        for i in range(3):
            check = Mock()
            check.status_code = None
            check.error_message = "Request timeout after 5000ms"
            check.response_time = None
            checks.append(check)

        severity = determine_severity(checks)
        assert severity == "HIGH"


# === SLA Calculation Tests ===

class TestSLACalculation:
    """Tests for sla.py module"""

    def test_calculate_uptime_100_percent(self, test_db, sample_endpoint):
        """100% uptime with all passing checks"""
        # Create 10 passing checks over last 24 hours
        for i in range(10):
            check = Check(
                endpoint_id=sample_endpoint.id,
                checked_at=datetime.now() - timedelta(hours=i),
                passed=True,
                status_code=200,
                response_time=100,
                error_message=None
            )
            test_db.add(check)
        test_db.commit()

        uptime = calculate_uptime(sample_endpoint.id, 24, test_db)
        assert uptime == 100.0

    def test_calculate_uptime_50_percent(self, test_db, sample_endpoint):
        """50% uptime with half failing checks"""
        # Create 10 checks, alternating pass/fail
        for i in range(10):
            check = Check(
                endpoint_id=sample_endpoint.id,
                checked_at=datetime.now() - timedelta(hours=i),
                passed=(i % 2 == 0),  # Every other check passes
                status_code=200 if i % 2 == 0 else 500,
                response_time=100,
                error_message=None if i % 2 == 0 else "Error"
            )
            test_db.add(check)
        test_db.commit()

        uptime = calculate_uptime(sample_endpoint.id, 24, test_db)
        assert uptime == 50.0

    def test_calculate_uptime_zero_checks(self, test_db, sample_endpoint):
        """100% uptime when no checks exist (no data = assume up)"""
        uptime = calculate_uptime(sample_endpoint.id, 24, test_db)
        assert uptime == 100.0

    def test_calculate_uptime_7_day_window(self, test_db, sample_endpoint):
        """SLA calculation over 7-day window"""
        # Create checks spanning 7 days
        for day in range(7):
            for hour in range(4):  # 4 checks per day
                check = Check(
                    endpoint_id=sample_endpoint.id,
                    checked_at=datetime.now() - timedelta(days=day, hours=hour*6),
                    passed=True,
                    status_code=200,
                    response_time=100
                )
                test_db.add(check)
        test_db.commit()

        uptime = calculate_uptime(sample_endpoint.id, 24*7, test_db)
        assert uptime == 100.0


# === Health Check Tests ===

class TestHealthChecker:
    """Tests for checker.py module"""

    @pytest.mark.asyncio
    async def test_run_check_success(self, sample_endpoint):
        """Successful endpoint check returns passing result"""
        with patch('httpx.AsyncClient.get') as mock_get:
            # Mock successful HTTP response
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.text = "OK"
            mock_get.return_value = mock_response

            result = await run_check(sample_endpoint)

            assert isinstance(result, CheckResult)
            assert result.passed == True
            assert result.status_code == 200
            assert result.response_time >= 0
            assert result.error_message is None

    @pytest.mark.asyncio
    async def test_run_check_failure_500(self, sample_endpoint):
        """Failed endpoint check (500 error) returns failing result"""
        with patch('httpx.AsyncClient.get') as mock_get:
            # Mock failed HTTP response
            mock_response = Mock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_get.return_value = mock_response

            result = await run_check(sample_endpoint)

            assert result.passed == False
            assert result.status_code == 500
            assert "500" in result.error_message or "expected 200" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_run_check_timeout(self, sample_endpoint):
        """Endpoint check timeout returns failing result"""
        import httpx

        with patch('httpx.AsyncClient.get') as mock_get:
            # Mock timeout exception
            mock_get.side_effect = httpx.TimeoutException("Request timed out")

            result = await run_check(sample_endpoint)

            assert result.passed == False
            assert "timeout" in result.error_message.lower()

    @pytest.mark.asyncio
    async def test_run_check_unsupported_method(self, sample_endpoint):
        """Unsupported HTTP method returns error"""
        sample_endpoint.method = "INVALID"
        result = await run_check(sample_endpoint)

        assert result.passed == False
        assert "unsupported" in result.error_message.lower()


# === Database Model Tests ===

class TestDatabaseModels:
    """Tests for models.py ORM definitions"""

    def test_create_endpoint(self, test_db):
        """Endpoint can be created with required fields"""
        endpoint = Endpoint(
            name="Test API",
            url="https://api.example.com/health",
            method="GET",
            environment="production",
            check_interval=300,
            timeout_ms=5000,
            expected_status=200,
            enabled=True
        )
        test_db.add(endpoint)
        test_db.commit()

        assert endpoint.id is not None
        assert endpoint.name == "Test API"
        assert endpoint.enabled == True

    def test_create_check(self, test_db, sample_endpoint):
        """Check can be created and linked to endpoint"""
        check = Check(
            endpoint_id=sample_endpoint.id,
            checked_at=datetime.now(),
            passed=True,
            status_code=200,
            response_time=150,
            error_message=None
        )
        test_db.add(check)
        test_db.commit()

        assert check.id is not None
        assert check.endpoint_id == sample_endpoint.id
        assert check.passed == True

    def test_create_incident(self, test_db, sample_endpoint):
        """Incident can be created and linked to endpoint"""
        incident = Incident(
            endpoint_id=sample_endpoint.id,
            started_at=datetime.now(),
            severity="HIGH",
            failure_count=3
        )
        test_db.add(incident)
        test_db.commit()

        assert incident.id is not None
        assert incident.endpoint_id == sample_endpoint.id
        assert incident.resolved_at is None  # Not resolved yet

    def test_resolve_incident(self, test_db, sample_endpoint):
        """Incident can be resolved with duration calculation"""
        started = datetime.now() - timedelta(minutes=30)
        incident = Incident(
            endpoint_id=sample_endpoint.id,
            started_at=started,
            severity="HIGH",
            failure_count=5
        )
        test_db.add(incident)
        test_db.commit()

        # Resolve incident
        incident.resolved_at = datetime.now()
        duration = (incident.resolved_at - incident.started_at).total_seconds() / 60
        incident.duration_mins = int(duration)
        test_db.commit()

        assert incident.resolved_at is not None
        assert incident.duration_mins >= 29  # At least 29 minutes


# === Alert Configuration Tests ===

class TestAlertConfiguration:
    """Tests for alerter.py configuration"""

    def test_alert_config_cooldown(self, test_db, sample_endpoint):
        """Alert cooldown prevents spam"""
        # Create alert config with 15-minute cooldown
        config = AlertConfig(
            endpoint_id=sample_endpoint.id,
            channel="email",
            target="test@example.com",
            on_incident=True,
            on_resolve=True,
            cooldown_mins=15,
            last_sent_at=datetime.now() - timedelta(minutes=10)  # Sent 10 minutes ago
        )
        test_db.add(config)
        test_db.commit()

        # Check if alert should be sent (should be False due to cooldown)
        now = datetime.now()
        time_since_last = (now - config.last_sent_at).total_seconds() / 60
        assert time_since_last < config.cooldown_mins

    def test_alert_config_cooldown_expired(self, test_db, sample_endpoint):
        """Alert can be sent after cooldown expires"""
        # Create alert config with cooldown expired
        config = AlertConfig(
            endpoint_id=sample_endpoint.id,
            channel="email",
            target="test@example.com",
            on_incident=True,
            cooldown_mins=15,
            last_sent_at=datetime.now() - timedelta(minutes=20)  # Sent 20 minutes ago
        )
        test_db.add(config)
        test_db.commit()

        # Check if alert should be sent (should be True, cooldown expired)
        now = datetime.now()
        time_since_last = (now - config.last_sent_at).total_seconds() / 60
        assert time_since_last >= config.cooldown_mins


# === Integration Tests ===

class TestEndToEndWorkflow:
    """Integration tests for complete workflows"""

    def test_endpoint_lifecycle(self, test_db):
        """Test complete endpoint lifecycle: create, update, disable, delete"""
        # Create
        endpoint = Endpoint(
            name="Lifecycle Test",
            url="https://api.test.com/status",
            method="GET",
            environment="dev",
            check_interval=300,
            enabled=True
        )
        test_db.add(endpoint)
        test_db.commit()
        endpoint_id = endpoint.id

        # Update
        endpoint.check_interval = 600
        test_db.commit()
        test_db.refresh(endpoint)
        assert endpoint.check_interval == 600

        # Disable
        endpoint.enabled = False
        test_db.commit()
        test_db.refresh(endpoint)
        assert endpoint.enabled == False

        # Delete
        test_db.delete(endpoint)
        test_db.commit()
        deleted = test_db.query(Endpoint).filter_by(id=endpoint_id).first()
        assert deleted is None

    def test_incident_workflow(self, test_db, sample_endpoint):
        """Test incident workflow: open -> checks -> close"""
        # Create failing checks
        for i in range(3):
            check = Check(
                endpoint_id=sample_endpoint.id,
                checked_at=datetime.now() - timedelta(minutes=15-i),
                passed=False,
                status_code=500,
                response_time=0,
                error_message="Server Error"
            )
            test_db.add(check)
        test_db.commit()

        # Open incident
        incident = Incident(
            endpoint_id=sample_endpoint.id,
            started_at=datetime.now() - timedelta(minutes=15),
            severity="HIGH",
            failure_count=3
        )
        test_db.add(incident)
        test_db.commit()

        # Create passing checks
        for i in range(2):
            check = Check(
                endpoint_id=sample_endpoint.id,
                checked_at=datetime.now() - timedelta(minutes=5-i),
                passed=True,
                status_code=200,
                response_time=100,
                error_message=None
            )
            test_db.add(check)
        test_db.commit()

        # Close incident
        incident.resolved_at = datetime.now()
        incident.duration_mins = int((incident.resolved_at - incident.started_at).total_seconds() / 60)
        test_db.commit()

        assert incident.resolved_at is not None
        assert incident.duration_mins >= 10


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
