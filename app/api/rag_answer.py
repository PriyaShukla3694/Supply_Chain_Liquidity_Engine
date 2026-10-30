# -*- coding: utf-8 -*-
"""RAG Answer Generation API Router.

Provides a protected ``POST /rag/answer`` endpoint that retrieves relevant
document chunks and generates a grounded answer using the OpenAI LLM.
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.api.deps import get_current_user, get_db
from app.models.user import User
from app.schemas.answer import AnswerRequest, AnswerResponse
from app.services import rag_retrieval as rag
from app.services.llm_answer import generate_answer

router = APIRouter(prefix="/rag", tags=["RAG"])

@router.post(
    "/answer",
    response_model=AnswerResponse,
    status_code=status.HTTP_200_OK,
    summary="Generate a grounded answer for a user query using retrieved RAG chunks",
)
async def answer(
    payload: AnswerRequest,
    db: "Session" = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Retrieve relevant chunks and generate an LLM answer.

    Steps:
    1. Retrieve up to ``payload.limit`` chunks for ``payload.query``.
    2. If no chunks are found, return a predefined insufficient‑evidence answer
       without invoking the LLM.
    3. Otherwise call :func:`app.services.llm_answer.generate_answer` to obtain a
       grounded answer and citations.
    """
    # Retrieve chunks – the service validates query, limit, and company isolation.
    chunks = rag.retrieve_chunks(
        query=payload.query,
        db=db,
        user=user,
        limit=payload.limit,
    )

    if not chunks:
        # No evidence – respond directly.
        return AnswerResponse(
            answer="I don't have enough information to answer that question.",
            citations=[],
            source_chunks=[],
        )

    # Generate answer via OpenAI – may raise HTTPException on config/provider errors.
    try:
        result = await generate_answer(query=payload.query, chunks=chunks)
    except HTTPException as exc:
        # Propagate FastAPI HTTP errors unchanged.
        raise exc
    except Exception as exc:
        # Unexpected errors become service‑unavailable.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Failed to generate answer.",
        ) from exc

    return AnswerResponse(
        answer=result["answer"],
        citations=result["citations"],
        source_chunks=result["source_chunks"],
    )
