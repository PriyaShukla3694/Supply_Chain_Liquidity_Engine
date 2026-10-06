import pytest
import requests
from sqlalchemy import create_engine, text

from app.main import verify_password, get_password_hash
from app.core.config import settings


# =====================================================================
# UNIT TESTS (Marked as unit tests only)
# =====================================================================

@pytest.mark.unit
def test_unit_config_fallback_and_defaults():
    """Unit test: Verifies configuration defaults and DATABASE_URL resolution."""
    assert settings.postgres_user == "postgres"
    assert settings.postgres_password == "postgres"
    assert settings.postgres_db == "liquidity_engine"
    assert "postgresql://" in settings.DATABASE_URL


@pytest.mark.unit
def test_unit_password_hashing_with_bcrypt():
    """Unit test: Verifies password hashing and verification using pinned bcrypt."""
    password = "secretpassword123"
    hashed = get_password_hash(password)
    assert verify_password(password, hashed) is True
    assert verify_password("wrongpassword", hashed) is False


# =====================================================================
# REAL DATABASE INTEGRATION TESTS (No mocks - hits real database)
# =====================================================================

@pytest.mark.integration
def test_real_db_direct_query():
    """Integration test: Connects directly to the real PostgreSQL database and runs SELECT 1."""
    engine = create_engine(settings.DATABASE_URL)
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
        assert result == 1


@pytest.mark.integration
def test_real_health_endpoints_http():
    """Integration test: Hits live running backend HTTP server /health and /health/db."""
    res_health = requests.get("http://localhost:8000/health", timeout=5)
    assert res_health.status_code == 200
    assert res_health.json()["status"] == "healthy"

    res_db = requests.get("http://localhost:8000/health/db", timeout=5)
    assert res_db.status_code == 200
    assert res_db.json()["status"] == "healthy"
    assert res_db.json()["database"] == "connected"
