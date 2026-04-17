"""Expense schemas."""
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ExpenseCreate(BaseModel):
    company_id: int
    amount: float
    currency: str = "USD"
    description: str
    expense_date: date
    category: str | None = None
    receipt_attachment_id: int | None = None
    payment_id: int | None = None


class ExpenseUpdate(BaseModel):
    amount: float | None = None
    currency: str | None = None
    description: str | None = None
    expense_date: date | None = None
    category: str | None = None
    receipt_attachment_id: int | None = None
    payment_id: int | None = None


class ExpenseResponse(BaseModel):
    id: int
    company_id: int
    amount: float
    currency: str
    description: str
    expense_date: date
    category: str | None = None
    receipt_attachment_id: int | None = None
    payment_id: int | None = None
    created_by_id: int | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ExpenseListResponse(BaseModel):
    items: list[ExpenseResponse]
    total: int
    page: int
    page_size: int
    pages: int


class ExpenseTotalsResponse(BaseModel):
    total_amount: float
    currency: str
    count: int
    by_category: dict[str, float]
