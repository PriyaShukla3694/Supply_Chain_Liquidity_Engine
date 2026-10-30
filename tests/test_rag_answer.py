
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_db
from app.main import app


class FakeUser:
    id = 1
    company_id = 1
    email = "test@example.com"
    is_active = True
    is_superuser = False
    role = "admin"


def override_get_current_user():
    return FakeUser()


def override_get_db():
    yield None


@pytest.fixture
def client():
    # Preserve existing overrides so these tests do not interfere
    # with other tests in the full suite.
    previous_overrides = app.dependency_overrides.copy()

    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous_overrides)


@pytest.fixture
def retrieved_chunks():
    return [
        {
            "document_name": "discount_policy.pdf",
            "document_type": "policy",
            "version": "1.0",
            "chunk_index": 0,
            "chunk_text": "Eligible invoices may receive discounts.",
            "distance": 0.2,
        }
    ]


def test_answer_success(client, retrieved_chunks):
    expected_result = {
        "answer": "Eligible invoices may receive discounts [1].",
        "citations": [
            {
                "index": 1,
                "document_name": "discount_policy.pdf",
                "document_type": "policy",
                "version": "1.0",
                "chunk_index": 0,
            }
        ],
        "source_chunks": retrieved_chunks,
    }

    with (
        patch(
            "app.api.rag_answer.rag.retrieve_chunks",
            return_value=retrieved_chunks,
        ) as mock_retrieve,
        patch(
            "app.api.rag_answer.generate_answer",
            return_value=expected_result,
        ) as mock_generate,
    ):
        response = client.post(
            "/rag/answer",
            json={"query": "What is the discount policy?"},
        )

    assert response.status_code == 200, response.text

    data = response.json()
    assert data["answer"] == expected_result["answer"]
    assert len(data["citations"]) == 1
    assert data["citations"][0]["index"] == 1
    assert data["citations"][0]["document_name"] == "discount_policy.pdf"
    assert data["source_chunks"] == retrieved_chunks

    mock_retrieve.assert_called_once()
    mock_generate.assert_awaited_once()


def test_answer_no_chunks(client):
    with (
        patch(
            "app.api.rag_answer.rag.retrieve_chunks",
            return_value=[],
        ) as mock_retrieve,
        patch(
            "app.api.rag_answer.generate_answer",
        ) as mock_generate,
    ):
        response = client.post(
            "/rag/answer",
            json={"query": "Any query"},
        )

    assert response.status_code == 200, response.text

    data = response.json()
    assert data["answer"] == (
        "I don't have enough information to answer that question."
    )
    assert data["citations"] == []
    assert data["source_chunks"] == []

    mock_retrieve.assert_called_once()
    mock_generate.assert_not_awaited()


def test_unauthenticated():
    # No authentication override here: verify the real auth dependency.
    with TestClient(app) as unauthenticated_client:
        response = unauthenticated_client.post(
            "/rag/answer",
            json={"query": "Any query"},
        )

    assert response.status_code == 401, response.text
