# -*- coding: utf-8 -*-
"""RAG Document Ingestion API router.

Provides a protected ``POST /rag/ingest`` endpoint that validates an uploaded
UTF‑8 text or markdown file, derives the company and uploader from the
authenticated user, and forwards the data to ``app.services.rag_ingestion.ingest_document``.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, status, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.services import rag_ingestion

# ---------------------------------------------------------------------------
# Request and response models
# ---------------------------------------------------------------------------

class DocumentIngestResponse(BaseModel):
    """Response schema reflecting the persisted ``Document`` model.

    Fields are a subset of the ORM model that are safe to expose via the API.
    ``version`` is required (the ORM column is non‑nullable).
    """

    id: int
    document_name: str
    document_type: str
    version: str
    effective_date: Optional[date] = None
    active_status: bool = True
    uploaded_by: Optional[int] = None
    created_at: datetime
    file_size: int

    class Config:
        orm_mode = True

# ---------------------------------------------------------------------------
# Router definition
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/rag", tags=["RAG"])


@router.post(
    "/ingest",
    response_model=DocumentIngestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Ingest a new policy/contract/SOP document for the authenticated user's company",
)
async def ingest(
    file: UploadFile = File(..., description="UTF‑8 .txt or .md file (max 2 MiB)"),
    document_type: str = Form(..., description="One of: policy, contract, sop"),
    version: str = Form("1.0", description="Document version string"),
    effective_date: Optional[date] = Form(None, description="Optional effective date"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Validate the upload, enforce company isolation, and persist the document.

    * ``company_id`` and ``uploaded_by`` are taken **exclusively** from the
      authenticated ``user`` – the client cannot supply them.
    * Validation mirrors ``rag_ingestion.ingest_document``; we convert any
      ``ValueError`` raised by the service into a clear ``400`` response.
    * Unexpected errors are logged and turned into a generic ``503`` response
      to avoid leaking internal details.
    """

    # -------------------------------------------------------------------
    # 1️⃣ Basic user checks – company must be present.
    # -------------------------------------------------------------------
    if not getattr(user, "company_id", None):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not belong to a company and cannot ingest documents.",
        )

    # -------------------------------------------------------------------
    # 2️⃣ Read file content **once**, enforce size limit, and ensure closure.
    # -------------------------------------------------------------------
    try:
        # Read up to limit+1 bytes to detect overflow without loading the whole file.
        content = await file.read(rag_ingestion.MAX_FILE_SIZE_BYTES + 1)
    finally:
        # Ensure the temporary file is always closed.
        await file.close()

    if len(content) > rag_ingestion.MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File exceeds the 2 MiB size limit.",
        )

    # -------------------------------------------------------------------
    # 3️⃣ Delegate to the ingestion service, handling its validation errors.
    # -------------------------------------------------------------------
    try:
        document = rag_ingestion.ingest_document(
            db=db,
            company_id=int(user.company_id),
            document_name=file.filename,
            document_type=document_type,
            content=content,
            uploaded_by=int(user.id) if getattr(user, "id", None) else None,
            version=version,
            effective_date=effective_date,
        )
        # Ensure the returned document includes the correct file size for API response
        document.file_size = len(content)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to ingest document at this time.",
        ) from exc

    return document
