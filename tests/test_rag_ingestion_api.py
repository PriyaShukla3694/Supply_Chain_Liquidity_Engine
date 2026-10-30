import io
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException, status
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.main import app
from app.services import rag_ingestion


client = TestClient(app)


# ---------------------------------------------------------
# Test helpers
# ---------------------------------------------------------

class DummyUser:
    def __init__(
        self,
        id: int = 1,
        company_id: int | None = 1,
        is_active: bool = True,
    ):
        self.id = id
        self.company_id = company_id
        self.is_active = is_active


class DummyDocument:
    def __init__(self, **kwargs):
        defaults = {
            "id": 123,
            "document_name": "test.txt",
            "document_type": "policy",
            "version": "1.0",
            "effective_date": None,
            "active_status": True,
            "uploaded_by": 1,
            "created_at": datetime.now(timezone.utc),
            "file_size": 0,
        }
        defaults.update(kwargs)
        self.__dict__.update(defaults)


# ---------------------------------------------------------
# Dependency overrides
# ---------------------------------------------------------

@pytest.fixture(autouse=True)
def override_dependencies(monkeypatch):
    # Mock database and authenticated user.
    # monkeypatch automatically restores previous overrides.
    monkeypatch.setitem(
        app.dependency_overrides,
        get_db,
        lambda: MagicMock(),
    )
    monkeypatch.setitem(
        app.dependency_overrides,
        get_current_user,
        lambda: DummyUser(),
    )


# ---------------------------------------------------------
# Successful ingestion
# ---------------------------------------------------------

def test_successful_ingest(monkeypatch):
    file_content = b"short policy content"

    dummy_doc = DummyDocument(
        document_name="mydoc.txt",
        document_type="policy",
        version="2.1",
        file_size=len(file_content),
    )

    def fake_ingest_document(*args, **kwargs):
        assert kwargs["company_id"] == 1
        assert kwargs["uploaded_by"] == 1
        assert kwargs["document_name"] == "mydoc.txt"
        assert kwargs["content"] == file_content
        return dummy_doc

    monkeypatch.setattr(
        rag_ingestion,
        "ingest_document",
        fake_ingest_document,
    )

    response = client.post(
        "/rag/ingest",
        files={
            "file": (
                "mydoc.txt",
                io.BytesIO(file_content),
                "text/plain",
            )
        },
        data={
            "document_type": "policy",
            "version": "2.1",
        },
    )

    assert response.status_code == status.HTTP_201_CREATED

    data = response.json()
    assert data["id"] == 123
    assert data["document_name"] == "mydoc.txt"
    assert data["document_type"] == "policy"
    assert data["version"] == "2.1"
    assert data["file_size"] == len(file_content)


# ---------------------------------------------------------
# Oversized upload
# ---------------------------------------------------------

def test_oversized_file(monkeypatch):
    oversized = b"a" * (
        rag_ingestion.MAX_FILE_SIZE_BYTES + 1
    )

    ingest_called = False

    def fake_ingest_document(*args, **kwargs):
        nonlocal ingest_called
        ingest_called = True
        raise AssertionError(
            "Ingestion service should not run for oversized files."
        )

    monkeypatch.setattr(
        rag_ingestion,
        "ingest_document",
        fake_ingest_document,
    )

    response = client.post(
        "/rag/ingest",
        files={
            "file": (
                "big.txt",
                io.BytesIO(oversized),
                "text/plain",
            )
        },
        data={"document_type": "policy"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert "size limit" in response.json()["detail"].lower()
    assert ingest_called is False


# ---------------------------------------------------------
# Service validation errors
# ---------------------------------------------------------

@pytest.mark.parametrize(
    "exc_msg",
    [
        "Only .txt and .md files are supported.",
        "The uploaded file is empty.",
        "Invalid UTF-8 encoding.",
    ],
)
def test_service_validation_error(monkeypatch, exc_msg):
    def raise_validation_error(*args, **kwargs):
        raise ValueError(exc_msg)

    monkeypatch.setattr(
        rag_ingestion,
        "ingest_document",
        raise_validation_error,
    )

    response = client.post(
        "/rag/ingest",
        files={
            "file": (
                "policy.txt",
                io.BytesIO(b"valid test content"),
                "text/plain",
            )
        },
        data={"document_type": "policy"},
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.json()["detail"] == exc_msg


# ---------------------------------------------------------
# Unexpected service error
# ---------------------------------------------------------

def test_unexpected_service_failure(monkeypatch):
    def broken_service(*args, **kwargs):
        raise RuntimeError("internal database details")

    monkeypatch.setattr(
        rag_ingestion,
        "ingest_document",
        broken_service,
    )

    response = client.post(
        "/rag/ingest",
        files={
            "file": (
                "policy.txt",
                io.BytesIO(b"valid test content"),
                "text/plain",
            )
        },
        data={"document_type": "policy"},
    )

    assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert response.json()["detail"] == (
        "Unable to ingest document at this time."
    )
    assert "internal database details" not in response.text


# ---------------------------------------------------------
# Authenticated user without a company
# ---------------------------------------------------------

def test_user_without_company(monkeypatch):
    monkeypatch.setitem(
        app.dependency_overrides,
        get_current_user,
        lambda: DummyUser(company_id=None),
    )

    response = client.post(
        "/rag/ingest",
        files={
            "file": (
                "policy.txt",
                io.BytesIO(b"test content"),
                "text/plain",
            )
        },
        data={"document_type": "policy"},
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "company" in response.json()["detail"].lower()


# ---------------------------------------------------------
# Unauthenticated request
# ---------------------------------------------------------

def test_unauthenticated(monkeypatch):
    def raise_unauthorized():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    monkeypatch.setitem(
        app.dependency_overrides,
        get_current_user,
        raise_unauthorized,
    )

    response = client.post(
        "/rag/ingest",
        files={
            "file": (
                "policy.txt",
                io.BytesIO(b"test content"),
                "text/plain",
            )
        },
        data={"document_type": "policy"},
    )

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------
# Retrieve endpoint registration
# ---------------------------------------------------------

def test_retrieve_endpoint_exists():
    matching_routes = [
        route
        for route in app.routes
        if getattr(route, "path", None) == "/rag/retrieve"
        and "POST" in (getattr(route, "methods", set()) or set())
    ]

    assert matching_routes, "POST /rag/retrieve is not registered"