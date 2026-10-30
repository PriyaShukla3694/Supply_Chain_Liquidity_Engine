# -*- coding: utf-8 -*-
"""RAG Retrieval API Router"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.services import rag_retrieval as rag
from app.models.user import User

# ---------------------------------------------------------------------------
# Pydantic request / response models
# ---------------------------------------------------------------------------

class RetrieveRequest(BaseModel):
    """Payload for a RAG retrieval request.

    * ``query`` – the search string supplied by the user.
    * ``limit`` – maximum number of chunks to return. Must be between 1 and 10.
    """

    query: str = Field(..., description="User search query")
    limit: int = Field(5, ge=1, le=10, description="Number of chunks to return (1‑10)")


class ChunkResponse(BaseModel):
    """Shape of a single chunk returned by the service.

    The fields mirror those produced by ``rag.retrieve_chunks``.
    ``version`` is non‑nullable according to the ``Document`` model.
    """

    document_name: str
    document_type: str
    version: str
    chunk_index: int
    chunk_text: str
    distance: float


# ---------------------------------------------------------------------------
# Router definition
# ---------------------------------------------------------------------------
router = APIRouter(prefix="/rag", tags=["RAG"])


@router.post(
    "/retrieve",
    response_model=List[ChunkResponse],
    status_code=status.HTTP_200_OK,
    summary="Retrieve relevant document chunks for a query",
)
def retrieve(
    payload: RetrieveRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Read‑only endpoint that forwards the request to the service.

    The authenticated user's ``company_id`` is derived from ``user`` – the client
    cannot supply a company identifier. The service already enforces the active
    document filter.
    """
    try:
        return rag.retrieve_chunks(
            query=payload.query,
            db=db,
            user=user,
            limit=payload.limit,
        )
    except HTTPException:
        # Propagate FastAPI HTTP errors unchanged – global handlers will format
        # the response consistently.
        raise
