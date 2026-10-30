
"""Ingest UTF-8 Markdown and text documents into the RAG store."""

from functools import lru_cache
from pathlib import Path
from typing import Optional
import logging

from sentence_transformers import SentenceTransformer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from sqlalchemy.exc import IntegrityError
import hashlib

logger = logging.getLogger(__name__)

MAX_FILE_SIZE_BYTES = 2 * 1024 * 1024  # 2 MB
CHUNK_SIZE = 1000
CHUNK_OVERLAP = 150
ALLOWED_EXTENSIONS = {".txt", ".md"}
ALLOWED_DOCUMENT_TYPES = {"policy", "contract", "sop"}


@lru_cache(maxsize=1)
def _get_embedding_model() -> SentenceTransformer:
    """Load the configured embedding model once per application process."""
    model = SentenceTransformer(settings.EMBEDDING_MODEL)

    if model.get_sentence_embedding_dimension() != 384:
        raise RuntimeError(
            "Embedding model must produce 384-dimensional vectors "
            "to match the document_chunks schema."
        )

    return model


def _split_text(
    text: str,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
) -> list[str]:
    """Split text into overlapping chunks, preferring nearby word boundaries."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive.")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be between 0 and chunk_size - 1.")

    text = text.strip()
    if not text:
        return []

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))

        if end < len(text):
            boundary = text.rfind(" ", start + chunk_size // 2, end)
            if boundary > start:
                end = boundary

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= len(text):
            break

        next_start = max(start + 1, end - overlap)
        start = next_start

    return chunks


def ingest_document(
    db: Session,
    *,
    company_id: int,
    document_name: str,
    document_type: str,
    content: bytes,
    uploaded_by: Optional[int] = None,
    version: str = "1.0",
    effective_date=None,
) -> Document:
    """
    Validate, embed, and persist one document and its chunks atomically.

    The caller must obtain company_id from trusted authenticated context,
    not directly from an untrusted upload request.
    """
    if not isinstance(company_id, int) or isinstance(company_id, bool) or company_id <= 0:
        raise ValueError("A valid company_id is required.")

    if not document_name or not document_name.strip():
        raise ValueError("document_name is required.")

    # Keep a filename only; do not trust or persist client-supplied paths.
    safe_name = Path(document_name.replace("\\", "/")).name.strip()
    suffix = Path(safe_name).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        raise ValueError("Only .txt and .md files are supported.")

    if document_type not in ALLOWED_DOCUMENT_TYPES:
        raise ValueError("document_type must be policy, contract, or sop.")

    if not isinstance(content, bytes):
        raise ValueError("content must be provided as bytes.")

    if not content:
        raise ValueError("The uploaded file is empty.")

    if len(content) > MAX_FILE_SIZE_BYTES:
        raise ValueError("File exceeds the 2 MB size limit.")

    try:
        text = content.decode("utf-8-sig").strip()
    except UnicodeDecodeError as exc:
        raise ValueError("File must contain valid UTF-8 text.") from exc

    if not text:
        raise ValueError("The document contains no usable text.")

    chunks = _split_text(text)
    if not chunks:
        raise ValueError("No text chunks could be created.")

    # Generate embeddings before opening a database write transaction.
    model = _get_embedding_model()
    vectors = model.encode(
        chunks,
        convert_to_numpy=True,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    if len(vectors) != len(chunks):
        raise RuntimeError("Embedding count does not match chunk count.")

    document = Document(
        company_id=company_id,
        document_name=safe_name,
        document_type=document_type,
        version=version,
        effective_date=effective_date,
        active_status=True,
        file_path=None,
        mime_type="text/markdown" if suffix == ".md" else "text/plain",
        file_size=len(content),
        content_hash=hashlib.sha256(content).hexdigest(),
        uploaded_by=uploaded_by,
    )

    try:
        db.add(document)
        db.flush()  # Assign document.id without committing.

        chunk_records = [
            DocumentChunk(
                document_id=document.id,
                chunk_index=index,
                chunk_text=chunk,
                embedding=vector.tolist(),
                metadata_json={
                    "document_name": safe_name,
                    "document_type": document_type,
                    "version": version,
                    "chunk_index": index,
                },
            )
            for index, (chunk, vector) in enumerate(zip(chunks, vectors))
        ]

        db.add_all(chunk_records)
        db.commit()
        db.refresh(document)

        return document

    except IntegrityError as exc:
        db.rollback()
        # Detect duplicate content violation
        constraint_name = None
        # SQLAlchemy (PostgreSQL) may expose the constraint name via exc.orig.diag.constraint_name
        if exc.orig is not None:
            diag = getattr(exc.orig, 'diag', None)
            if diag is not None:
                constraint_name = getattr(diag, 'constraint_name', None)
        # Fallback: inspect exception message for generic duplicate key indication (used by tests)
        msg = str(exc).lower()
        if constraint_name == 'uq_documents_company_type_version_hash' or 'duplicate key' in msg:
            raise ValueError("Duplicate document content for this company, type and version.") from exc
        # If it's another integrity error, re‑raise the original exception
        raise
    except Exception as exc:
        db.rollback()
        # Unexpected error; propagate after rolling back
        raise
