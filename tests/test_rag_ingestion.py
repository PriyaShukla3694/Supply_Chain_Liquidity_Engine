import numpy as np
import pytest

from app.services import rag_ingestion as rag


class FakeDB:
    """Minimal database-session fake for isolated unit tests."""

    def __init__(self, fail_commit=False):
        self.added = []
        self.added_many = []
        self.fail_commit = fail_commit
        self.rolled_back = False
        self.committed = False

    def add(self, obj):
        self.added.append(obj)

    def flush(self):
        for obj in self.added:
            if hasattr(obj, "document_name"):
                obj.id = 123

    def add_all(self, objects):
        self.added_many.extend(objects)

    def commit(self):
        if self.fail_commit:
            raise RuntimeError("Simulated database failure")
        self.committed = True

    def refresh(self, obj):
        pass

    def rollback(self):
        self.rolled_back = True


class FakeEmbeddingModel:
    """Fake embedding model that avoids loading the real model in tests."""

    def get_sentence_embedding_dimension(self):
        return 384

    def encode(self, chunks, **kwargs):
        return np.zeros((len(chunks), 384), dtype=np.float32)


@pytest.fixture
def fake_model(monkeypatch):
    monkeypatch.setattr(
        rag,
        "_get_embedding_model",
        lambda: FakeEmbeddingModel(),
    )


def ingest(db, content=b"Policy content for testing.", name="policy.txt"):
    return rag.ingest_document(
        db,
        company_id=1,
        document_name=name,
        document_type="policy",
        content=content,
        uploaded_by=7,
    )


def test_successful_ingestion_saves_document_and_chunks(fake_model):
    db = FakeDB()

    document = ingest(
        db,
        b"Payment policy: invoices must be undisputed.",
    )

    assert document.id == 123
    assert document.company_id == 1
    assert document.document_name == "policy.txt"
    assert db.committed
    assert not db.rolled_back
    assert len(db.added_many) >= 1
    assert db.added_many[0].document_id == 123
    assert len(db.added_many[0].embedding) == 384


@pytest.mark.parametrize(
    "name,content",
    [
        ("policy.pdf", b"PDF not supported"),
        ("policy.txt", b""),
        ("policy.txt", b"   \n\t "),
        ("policy.txt", b"\xff\xfe\xfa"),
    ],
    ids=[
        "unsupported-extension",
        "empty-file",
        "whitespace-only-file",
        "invalid-utf8",
    ],
)
def test_invalid_files_are_rejected_before_database_write(
    fake_model,
    name,
    content,
):
    db = FakeDB()

    with pytest.raises(ValueError):
        ingest(db, content, name)

    assert db.added == []
    assert db.added_many == []
    assert not db.committed


def test_oversized_file_is_rejected_before_database_write(fake_model):
    db = FakeDB()
    content = b"x" * (rag.MAX_FILE_SIZE_BYTES + 1)

    with pytest.raises(ValueError, match="2 MB"):
        ingest(db, content)

    assert db.added == []
    assert db.added_many == []
    assert not db.committed


def test_invalid_company_id_is_rejected(fake_model):
    db = FakeDB()

    with pytest.raises(ValueError, match="company_id"):
        rag.ingest_document(
            db,
            company_id=0,
            document_name="policy.txt",
            document_type="policy",
            content=b"Policy content",
        )

    assert db.added == []


def test_invalid_document_type_is_rejected(fake_model):
    db = FakeDB()

    with pytest.raises(ValueError, match="document_type"):
        rag.ingest_document(
            db,
            company_id=1,
            document_name="policy.txt",
            document_type="unknown",
            content=b"Policy content",
        )

    assert db.added == []


def test_database_failure_rolls_back(fake_model):
    db = FakeDB(fail_commit=True)

    with pytest.raises(RuntimeError, match="Simulated database failure"):
        ingest(db)

    assert db.rolled_back
    assert not db.committed


def test_chunking_preserves_text_and_uses_overlap():
    text = "word " * 500
    chunks = rag._split_text(text)

    assert len(chunks) > 1
    assert all(chunks)
    assert all(len(chunk) <= rag.CHUNK_SIZE for chunk in chunks)

    # Verify that consecutive chunks share overlapping text.
    assert chunks[0][-rag.CHUNK_OVERLAP:].strip().split()[-1] == (
        chunks[1][:rag.CHUNK_OVERLAP].strip().split()[0]
    )


def test_unsupported_chunk_parameters_are_rejected():
    with pytest.raises(ValueError):
        rag._split_text("some text", chunk_size=0)

    with pytest.raises(ValueError):
        rag._split_text("some text", chunk_size=10, overlap=10)
