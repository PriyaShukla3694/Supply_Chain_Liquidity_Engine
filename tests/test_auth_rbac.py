from datetime import timedelta
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.db.session import Base, get_db
from app.core.security import create_access_token, decode_access_token
from app.models.user import User
from app.models.company import Company


@pytest.fixture
def client_and_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as client:
        yield client, TestingSession
    app.dependency_overrides.clear()


@pytest.mark.unit
def test_register_first_admin(client_and_db):
    client, Session = client_and_db

    # Register first user when database has 0 users
    res = client.post(
        "/register",
        json={"username": "alice_admin", "password": "supersecurepassword123", "email": "alice@example.com"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["username"] == "alice_admin"
    assert data["role"] == "admin"
    assert data["company_id"] is not None
    assert "hashed_password" not in data
    assert "password" not in data

    # Verify company was automatically created
    with Session() as db:
        user = db.query(User).filter_by(username="alice_admin").first()
        assert user is not None
        assert user.role == "admin"
        assert user.company_id is not None
        company = db.query(Company).filter_by(id=user.company_id).first()
        assert company is not None


@pytest.mark.unit
def test_login_success(client_and_db):
    client, _ = client_and_db

    # 1. Register first admin
    client.post(
        "/register",
        json={"username": "bob_admin", "password": "password123"},
    )

    # 2. Login with valid credentials using OAuth2 form data
    res = client.post(
        "/login",
        data={"username": "bob_admin", "password": "password123"},
    )
    assert res.status_code == 200
    token_data = res.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"

    # Verify JWT payload
    payload = decode_access_token(token_data["access_token"])
    assert payload["sub"] == "bob_admin"
    assert payload["role"] == "admin"
    assert "company_id" in payload


@pytest.mark.unit
def test_wrong_password(client_and_db):
    client, _ = client_and_db

    client.post(
        "/register",
        json={"username": "charlie_admin", "password": "correct_password"},
    )

    res = client.post(
        "/login",
        data={"username": "charlie_admin", "password": "incorrect_password"},
    )
    assert res.status_code == 401
    assert "Incorrect username or password" in res.json()["detail"]


@pytest.mark.unit
def test_inactive_user_rejected(client_and_db):
    client, Session = client_and_db

    # Register admin and deactivate account
    client.post(
        "/register",
        json={"username": "dave_user", "password": "password123"},
    )
    with Session() as db:
        user = db.query(User).filter_by(username="dave_user").first()
        user.is_active = False
        db.commit()

    # Login should reject inactive user
    res = client.post(
        "/login",
        data={"username": "dave_user", "password": "password123"},
    )
    assert res.status_code == 400
    assert "Inactive user account" in res.json()["detail"]

    # Even with an active token, get_current_user should reject inactive user
    token = create_access_token(data={"sub": "dave_user", "role": "admin"})
    res_me = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_me.status_code == 403
    assert "Inactive user account" in res_me.json()["detail"]


@pytest.mark.unit
def test_invalid_and_expired_token(client_and_db):
    client, _ = client_and_db

    # Invalid token string
    res_invalid = client.get(
        "/users/me",
        headers={"Authorization": "Bearer not.a.valid.jwt.token"},
    )
    assert res_invalid.status_code == 401

    # Expired token
    expired_token = create_access_token(
        data={"sub": "anyuser", "role": "admin"},
        expires_delta=timedelta(minutes=-15),
    )
    res_expired = client.get(
        "/users/me",
        headers={"Authorization": f"Bearer {expired_token}"},
    )
    assert res_expired.status_code == 401


@pytest.mark.unit
def test_analyst_blocked_from_admin_ping(client_and_db):
    client, Session = client_and_db

    # 1. Register admin
    client.post("/register", json={"username": "admin1", "password": "password123"})
    admin_login = client.post("/login", data={"username": "admin1", "password": "password123"}).json()
    admin_token = admin_login["access_token"]

    # 2. Admin registers an analyst
    client.post(
        "/register",
        json={"username": "analyst1", "password": "password123", "role": "analyst"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    analyst_login = client.post("/login", data={"username": "analyst1", "password": "password123"}).json()
    analyst_token = analyst_login["access_token"]

    # 3. Analyst attempts to access /admin/ping -> 403 Forbidden
    res_admin_ping = client.get(
        "/admin/ping",
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    assert res_admin_ping.status_code == 403
    assert "Required roles: admin" in res_admin_ping.json()["detail"]

    # 4. Analyst attempts to access /finance/ping -> 403 Forbidden
    res_fin_ping = client.get(
        "/finance/ping",
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    assert res_fin_ping.status_code == 403


@pytest.mark.unit
def test_admin_and_finance_roles_allowed(client_and_db):
    client, _ = client_and_db

    # Register first admin
    client.post("/register", json={"username": "admin_root", "password": "password123"})
    admin_token = client.post("/login", data={"username": "admin_root", "password": "password123"}).json()["access_token"]

    # Admin accesses /admin/ping
    res_admin = client.get("/admin/ping", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin.status_code == 200
    assert res_admin.json()["message"] == "admin pong"

    # Admin accesses /finance/ping
    res_fin = client.get("/finance/ping", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_fin.status_code == 200
    assert res_fin.json()["message"] == "finance pong"

    # Admin creates finance manager
    client.post(
        "/register",
        json={"username": "fin_manager1", "password": "password123", "role": "finance_manager"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    fin_token = client.post("/login", data={"username": "fin_manager1", "password": "password123"}).json()["access_token"]

    # Finance Manager accesses /finance/ping -> 200
    res_fin_manager = client.get("/finance/ping", headers={"Authorization": f"Bearer {fin_token}"})
    assert res_fin_manager.status_code == 200
    assert res_fin_manager.json()["message"] == "finance pong"

    # Finance Manager accesses /admin/ping -> 403
    res_fin_to_admin = client.get("/admin/ping", headers={"Authorization": f"Bearer {fin_token}"})
    assert res_fin_to_admin.status_code == 403


@pytest.mark.unit
def test_non_admin_cannot_create_users_and_role_validation(client_and_db):
    client, _ = client_and_db

    # Register first admin
    client.post("/register", json={"username": "first_admin", "password": "password123"})
    admin_token = client.post("/login", data={"username": "first_admin", "password": "password123"}).json()["access_token"]

    # Create an analyst
    client.post(
        "/register",
        json={"username": "regular_analyst", "password": "password123", "role": "analyst"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    analyst_token = client.post("/login", data={"username": "regular_analyst", "password": "password123"}).json()["access_token"]

    # Unauthenticated user attempts to create user when users already exist -> 401
    res_unauth = client.post(
        "/register",
        json={"username": "another_user", "password": "password123"},
    )
    assert res_unauth.status_code == 401

    # Non-admin (analyst) attempts to create user -> 403
    res_forbidden = client.post(
        "/register",
        json={"username": "another_user", "password": "password123"},
        headers={"Authorization": f"Bearer {analyst_token}"},
    )
    assert res_forbidden.status_code == 403

    # Admin attempts to create user with invalid role -> 400
    res_invalid_role = client.post(
        "/register",
        json={"username": "hacker", "password": "password123", "role": "supergod"},
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert res_invalid_role.status_code == 400
    assert "Invalid role" in res_invalid_role.json()["detail"]


@pytest.mark.unit
def test_users_me_endpoint(client_and_db):
    client, _ = client_and_db

    client.post("/register", json={"username": "me_user", "password": "password123", "email": "me@example.com"})
    token = client.post("/login", data={"username": "me_user", "password": "password123"}).json()["access_token"]

    res = client.get("/users/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 200
    data = res.json()
    assert data["username"] == "me_user"
    assert data["email"] == "me@example.com"
    assert data["role"] == "admin"
    assert data["company_id"] is not None
    assert "hashed_password" not in data
