"""Core schemas used across the CRM application."""

from typing import Generic, TypeVar, List, Optional
from pydantic import BaseModel, Field
from src.core.constants import DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE

T = TypeVar("T")


class TagBrief(BaseModel):
    """Brief tag representation for responses."""
    id: int
    name: str
    color: Optional[str] = None

    class Config:
        from_attributes = True


class ContactBrief(BaseModel):
    """Brief contact representation for related entity responses."""
    id: int
    full_name: str

    class Config:
        from_attributes = True


class CompanyBrief(BaseModel):
    """Brief company representation for related entity responses."""
    id: int
    name: str

    class Config:
        from_attributes = True


class OpportunityBrief(BaseModel):
    """Brief opportunity representation for related entity responses."""
    id: int
    name: str

    class Config:
        from_attributes = True


class QuoteBrief(BaseModel):
    """Brief quote representation for related entity responses."""
    id: int
    quote_number: str
    title: str
    total: float

    class Config:
        from_attributes = True


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response schema."""
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int

    @classmethod
    def create(
        cls,
        items: List[T],
        total: int,
        page: int,
        page_size: int,
    ) -> "PaginatedResponse[T]":
        """Factory method to create paginated response."""
        total_pages = (total + page_size - 1) // page_size if page_size > 0 else 0
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )


class PaginationParams(BaseModel):
    """Common pagination parameters."""
    page: int = Field(default=1, ge=1, description="Page number")
    page_size: int = Field(
        default=DEFAULT_PAGE_SIZE,
        ge=1,
        le=MAX_PAGE_SIZE,
        description="Items per page",
    )


class SuccessResponse(BaseModel):
    """Generic success response."""
    success: bool = True
    message: str = "Operation completed successfully"


class ErrorResponse(BaseModel):
    """Generic error response."""
    success: bool = False
    error: str
    detail: Optional[str] = None


class DeleteResponse(BaseModel):
    """Response for delete operations."""
    success: bool = True
    message: str = "Item deleted successfully"
    id: int
