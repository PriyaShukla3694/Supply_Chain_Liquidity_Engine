
"""RAG Retrieval Service.

Retrieves the most relevant document chunks for a user query using pgvector
similarity search while enforcing tenant isolation and active-document rules.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import Float
from sqlalchemy.orm import Session

from app.services.rag_ingestion import _get_embedding_model
from app.models.document import Document
from app.models.document_chunk import DocumentChunk
from app.models.user import User


logger = logging.getLogger(__name__)


def _validate_query(query: str) -> str:
    """Validate the incoming query string."""
    if not isinstance(query, str) or not query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query must be a non-empty string.",
        )

    query = query.strip()

    if len(query) > 2000:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query exceeds maximum length of 2,000 characters.",
        )

    return query


def _validate_user(user: User) -> int:
    """Ensure the user belongs to a company."""
    company_id = getattr(user, "company_id", None)

    if company_id is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not belong to a company and cannot perform retrieval.",
        )

    return int(company_id)


def _validate_limit(limit: int) -> int:
    """Validate the retrieval result limit."""
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Limit must be an integer between 1 and 10.",
        )

    return limit


def retrieve_chunks(
    query: str,
    db: Session,
    user: User,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Retrieve the nearest document chunks for the user's company."""
    query = _validate_query(query)
    company_id = _validate_user(user)
    limit = _validate_limit(limit)

    # Generate the query embedding.
    try:
        model = _get_embedding_model()
        query_vec_np = model.encode(
            [query],
            convert_to_numpy=True,
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0]
        query_vec = query_vec_np.tolist()

    except Exception as exc:
        logger.exception("Failed to generate RAG query embedding")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to process the retrieval query at this time.",
        ) from exc

    if len(query_vec) != 384:
        logger.error(
            "RAG embedding dimension mismatch: expected 384, got %d",
            len(query_vec),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Query embedding dimension mismatch.",
        )

    # pgvector <-> calculates Euclidean distance.
    distance_expr = DocumentChunk.embedding.op(
    "<->",
    return_type=Float,
)(query_vec)

    try:
        # Select individual fields rather than the full ORM entity.
        # This avoids loading the embedding column into the ORM result.
        stmt = (
            db.query(
                DocumentChunk.id,
                DocumentChunk.chunk_index,
                DocumentChunk.chunk_text,
                distance_expr.label("distance"),
                Document.document_name,
                Document.document_type,
                Document.version,
            )
            .join(
                Document,
                Document.id == DocumentChunk.document_id,
            )
            .filter(
                Document.company_id == company_id,
                Document.active_status.is_(True),
                DocumentChunk.embedding.is_not(None),
            )
            .order_by(distance_expr.asc())
            .limit(limit)
        )

        rows = stmt.all()

    except Exception as exc:
        logger.exception("RAG retrieval database query failed")

        try:
            db.rollback()
        except Exception:
            logger.exception("Database rollback failed after RAG retrieval error")

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to retrieve documents at this time.",
        ) from exc

    results: list[dict[str, Any]] = []

    for row in rows:
        results.append(
            {
                "document_name": row.document_name,
                "document_type": row.document_type,
                "version": row.version,
                "chunk_index": row.chunk_index,
                "chunk_text": row.chunk_text,
                "distance": float(row.distance),
            }
        )

    return results
