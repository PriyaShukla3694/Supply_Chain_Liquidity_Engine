import pytest
from sqlalchemy.exc import IntegrityError
from app.services import rag_ingestion as rag

class FakeDB:
    """Fake DB session that simulates duplicate constraint violation on duplicate content_hash."""

    def __init__(self):
        self.added = []
        self.added_many = []
        self.committed = False
        self.rolled_back = False
        self.existing_hashes = set()

    def add(self, obj):
        # Simulate duplicate detection based on content_hash attribute
        if hasattr(obj, "content_hash") and obj.content_hash in self.existing_hashes:
            raise IntegrityError("duplicate key value violates unique constraint", params={}, orig=None)
        if hasattr(obj, "content_hash"):
            self.existing_hashes.add(obj.content_hash)
        self.added.append(obj)

    def flush(self):
        for obj in self.added:
            if hasattr(obj, "document_name"):
                obj.id = 123

    def add_all(self, objects):
        self.added_many.extend(objects)

    def commit(self):
        self.committed = True

    def refresh(self, obj):
        pass

    def rollback(self):
        self.rolled_back = True

@pytest.fixture
def fake_model(monkeypatch):
    class FakeEmbeddingModel:
        def get_sentence_embedding_dimension(self):
            return 384
        def encode(self, chunks, **kwargs):
            import numpy as np
            return np.zeros((len(chunks), 384), dtype=np.float32)
    monkeypatch.setattr(rag, "_get_embedding_model", lambda: FakeEmbeddingModel())

def ingest(db, content=b"duplicate content", name="policy.txt"):
    return rag.ingest_document(
        db,
        company_id=1,
        document_name=name,
        document_type="policy",
        content=content,
        uploaded_by=7,
    )

def test_duplicate_content_is_rejected(fake_model):
    db = FakeDB()
    # First ingestion should succeed
    doc1 = ingest(db)
    assert doc1.id == 123
    assert db.committed
    assert not db.rolled_back

    # Reset flags for second attempt
    db.committed = False
    db.rolled_back = False

    # Second ingestion with same content should raise ValueError about duplicate
    with pytest.raises(ValueError, match="Duplicate document content"):
        ingest(db)
    # Ensure second attempt rolled back and did not commit
    assert not db.committed
    assert db.rolled_back
