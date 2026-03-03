"""Expense schemas."""
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, ConfigDict


class ExpenseCreate(BaseModel):
    company_id: int
    amount: float
    currency: str = "USD"
    description: str
    expense_date: date
    category: Optional[str] = None
    receipt_attachment_id: Optional[int] = None
    payment_id: Optional[int] = None


class ExpenseUpdate(BaseModel):
    amount: Optional[float] = None
    currency: Optional[str] = None
    description: Optional[str] = None
    expense_date: Optional[date] = None
    category: Optional[str] = None
    receipt_attachment_id: Optional[int] = None
    payment_id: Optional[int] = None


class ExpenseResponse(BaseModel):
    id: int
    company_id: int
    amount: float
    currency: str
    description: str
    expense_date: date
    category: Optional[str] = None
    receipt_attachment_id: Optional[int] = None
    payment_id: Optional[int] = None
    created_by_id: Optional[int] = None
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
