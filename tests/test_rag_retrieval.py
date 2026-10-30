
"""Unit tests for the RAG retrieval service.

These tests use a fake database session and embedding model.
They do not require a live PostgreSQL/pgvector instance.
"""

import pytest
import numpy as np
from fastapi import HTTPException, status

from app.services import rag_retrieval as rag


# ---------------------------------------------------------------------------
# Helper fakes
# ---------------------------------------------------------------------------

class FakeUser:
    def __init__(self, company_id=None):
        self.company_id = company_id


class FakeDocument:
    def __init__(self, id, company_id, active_status=True):
        self.id = id
        self.company_id = company_id
        self.active_status = active_status
        self.document_name = f"doc-{id}.txt"
        self.document_type = "policy"
        self.version = "1.0"


class FakeChunk:
    def __init__(self, document, index, text, distance):
        self.document = document
        self.chunk_index = index
        self.chunk_text = text
        self.embedding = None


class FakeSession:
    """Fake query session that applies captured retrieval filters."""

    def __init__(self, rows=None, raise_on_all=False):
        self._rows = rows or []
        self.raise_on_all = raise_on_all

        self.added = []
        self.added_many = []
        self.committed = False
        self.rolled_back = False

        self.captured_company_id = None
        self.captured_active_status = None

    def query(self, *args, **kwargs):
        return self

    def join(self, *args, **kwargs):
        return self

    def options(self, *args, **kwargs):
        return self

    def filter(self, *criteria, **kwargs):
        """Capture company and active-status filters from SQLAlchemy expressions."""
        for criterion in criteria:
            expression = str(criterion).lower()

            left = getattr(criterion, "left", None)
            right = getattr(criterion, "right", None)

            left_name = getattr(left, "name", None)
            right_value = getattr(right, "value", None)

            # Capture company_id equality filter.
            if "company_id" in expression:
                if right_value is not None:
                    self.captured_company_id = int(right_value)
                else:
                    # Fallback for SQLAlchemy expression representations.
                    import re

                    match = re.search(
                        r"company_id\s*=\s*(\d+)", expression
                    )
                    if match:
                        self.captured_company_id = int(match.group(1))

            # Capture active_status IS TRUE / IS FALSE.
            if "active_status" in expression:
                if " is true" in expression or expression.endswith("is true"):
                    self.captured_active_status = True
                elif " is false" in expression or expression.endswith("is false"):
                    self.captured_active_status = False
                elif left_name == "active_status" and right_value is not None:
                    self.captured_active_status = bool(right_value)
                else:
                    # SQLAlchemy may represent IS TRUE using a unary expression.
                    operator_name = getattr(
                        getattr(criterion, "operator", None),
                        "__name__",
                        "",
                    )
                    if operator_name == "is_true":
                        self.captured_active_status = True
                    elif operator_name == "is_false":
                        self.captured_active_status = False

        return self

    def order_by(self, *args, **kwargs):
        return self

    def limit(self, limit: int = None):
        """Record the requested limit for later enforcement in all()."""
        self._limit = limit
        return self

    def all(self):
        if self.raise_on_all:
            raise RuntimeError("simulated DB failure")

        from collections import namedtuple
        FakeResult = namedtuple('FakeResult', ['id', 'chunk_index', 'chunk_text', 'distance', 'document_name', 'document_type', 'version'])

        filtered = []
        for chunk, distance in self._rows:
            document = getattr(chunk, "document", None)
            if document is None:
                continue

            # Enforce the company filter.
            if (
                self.captured_company_id is not None
                and document.company_id != self.captured_company_id
            ):
                continue

            # Enforce the active-status filter.
            if (
                self.captured_active_status is not None
                and document.active_status != self.captured_active_status
            ):
                continue

            # Build a result row matching the production query shape.
            result = FakeResult(
                id=getattr(chunk, "id", None),
                chunk_index=chunk.chunk_index,
                chunk_text=chunk.chunk_text,
                distance=distance,
                document_name=getattr(document, "document_name", None),
                document_type=getattr(document, "document_type", None),
                version=getattr(document, "version", None),
            )
            filtered.append(result)

        # Apply stored limit if set.
        if getattr(self, "_limit", None) is not None:
            return filtered[: self._limit]
        return filtered

    def add(self, obj):
        self.added.append(obj)

    def add_all(self, objs):
        self.added_many.extend(objs)

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


# ---------------------------------------------------------------------------
# Mock embedding model
# ---------------------------------------------------------------------------

class DummyEmbeddingModel:
    def get_sentence_embedding_dimension(self):
        return 384

    def encode(self, texts, **kwargs):
        return np.ones((len(texts), 384), dtype=float)


@pytest.fixture(autouse=True)
def patch_embedding(monkeypatch):
    monkeypatch.setattr(
        rag, "_get_embedding_model", lambda: DummyEmbeddingModel()
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_successful_retrieval_returns_expected_fields_and_order():
    doc = FakeDocument(id=1, company_id=42)
    chunk1 = FakeChunk(doc, 0, "First chunk", 0.2)
    chunk2 = FakeChunk(doc, 1, "Second chunk", 0.5)

    db = FakeSession([(chunk1, 0.2), (chunk2, 0.5)])

    result = rag.retrieve_chunks(
        query="test", db=db, user=FakeUser(42), limit=5
    )

    assert len(result) == 2
    assert result[0]["chunk_text"] == "First chunk"
    assert result[0]["distance"] == 0.2
    assert result[1]["chunk_text"] == "Second chunk"

    for field in (
        "document_name",
        "document_type",
        "version",
        "chunk_index",
        "chunk_text",
        "distance",
    ):
        assert field in result[0]


def test_results_are_limited_by_limit_parameter():
    doc = FakeDocument(id=1, company_id=1)
    rows = [
        (FakeChunk(doc, i, f"c{i}", i), i)
        for i in range(10)
    ]

    result = rag.retrieve_chunks(
        query="any", db=FakeSession(rows), user=FakeUser(1), limit=3
    )

    assert len(result) == 3
    assert [item["distance"] for item in result] == [0, 1, 2]


def test_empty_and_whitespace_queries_raise_400():
    db = FakeSession()

    for query in ("", "   ", "\n\t"):
        with pytest.raises(HTTPException) as exc:
            rag.retrieve_chunks(query, db, FakeUser(1))

        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST


def test_oversized_query_raises_400():
    with pytest.raises(HTTPException) as exc:
        rag.retrieve_chunks("a" * 2001, FakeSession(), FakeUser(1))

    assert exc.value.status_code == status.HTTP_400_BAD_REQUEST


def test_user_without_company_id_raises_403():
    with pytest.raises(HTTPException) as exc:
        rag.retrieve_chunks("test", FakeSession(), FakeUser(None))

    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


def test_limit_out_of_range_raises_400():
    for limit in (0, -3, 11, 100):
        with pytest.raises(HTTPException) as exc:
            rag.retrieve_chunks(
                "test", FakeSession(), FakeUser(1), limit=limit
            )

        assert exc.value.status_code == status.HTTP_400_BAD_REQUEST


def test_inactive_documents_are_excluded():
    active_doc = FakeDocument(1, company_id=1, active_status=True)
    inactive_doc = FakeDocument(2, company_id=1, active_status=False)

    active_chunk = FakeChunk(active_doc, 0, "active", 0.1)
    inactive_chunk = FakeChunk(inactive_doc, 0, "inactive", 0.2)

    db = FakeSession([
        (active_chunk, 0.1),
        (inactive_chunk, 0.2),
    ])

    result = rag.retrieve_chunks("test", db, FakeUser(1))

    assert db.captured_active_status is True
    assert len(result) == 1
    assert result[0]["chunk_text"] == "active"


def test_documents_of_other_company_are_excluded():
    doc_a = FakeDocument(1, company_id=1)
    doc_b = FakeDocument(2, company_id=2)

    chunk_a = FakeChunk(doc_a, 0, "company one", 0.1)
    chunk_b = FakeChunk(doc_b, 0, "company two", 0.2)

    db = FakeSession([
        (chunk_a, 0.1),
        (chunk_b, 0.2),
    ])

    result = rag.retrieve_chunks("test", db, FakeUser(1))

    assert db.captured_company_id == 1
    assert len(result) == 1
    assert result[0]["document_name"] == doc_a.document_name


def test_embedding_dimension_mismatch_raises_500(monkeypatch):
    class BadDimModel:
        def encode(self, texts, **kwargs):
            return np.zeros((len(texts), 300), dtype=float)

    monkeypatch.setattr(
        rag, "_get_embedding_model", lambda: BadDimModel()
    )

    with pytest.raises(HTTPException) as exc:
        rag.retrieve_chunks("test", FakeSession(), FakeUser(1))

    assert exc.value.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_database_error_returns_503_and_rolls_back():
    db = FakeSession(raise_on_all=True)

    with pytest.raises(HTTPException) as exc:
        rag.retrieve_chunks("test", db, FakeUser(1))

    assert exc.value.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
    assert db.rolled_back is True


def test_no_database_writes_are_performed():
    doc = FakeDocument(1, company_id=1)
    chunk = FakeChunk(doc, 0, "test chunk", 0.1)

    db = FakeSession([(chunk, 0.1)])

    rag.retrieve_chunks("test", db, FakeUser(1))

    assert db.added == []
    assert db.added_many == []
    assert db.committed is False
    assert db.rolled_back is False
