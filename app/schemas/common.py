from typing import Generic, List, TypeVar
from fastapi import Query
from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int = Field(..., description="Total number of items matching filters")
    page: int = Field(..., ge=1, description="Current page number")
    page_size: int = Field(..., ge=1, le=100, description="Items per page")


class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Human-readable error description")
    code: str = Field(..., description="Machine-readable error code")


class PaginationParams:
    def __init__(
        self,
        page: int = Query(1, ge=1, description="Page number, must be >= 1"),
        page_size: int = Query(20, ge=1, le=100, description="Items per page, between 1 and 100"),
    ):
        self.page = page
        self.page_size = page_size
        self.offset = (page - 1) * page_size
        self.limit = page_size
