"""Expense API routes."""
from typing import Optional
from fastapi import APIRouter, HTTPException, Query, UploadFile, File
from src.core.constants import HTTPStatus
from src.core.router_utils import DBSession, CurrentUser, calculate_pages
from src.expenses.schemas import (
    ExpenseCreate, ExpenseUpdate, ExpenseResponse,
    ExpenseListResponse, ExpenseTotalsResponse,
)
from src.expenses.service import ExpenseService

router = APIRouter(prefix="/api/expenses", tags=["expenses"])


@router.get("", response_model=ExpenseListResponse)
async def list_expenses(
    current_user: CurrentUser,
    db: DBSession,
    company_id: int = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
):
    """List expenses for a company."""
    service = ExpenseService(db)
    expenses, total = await service.get_list(
        company_id=company_id,
        page=page,
        page_size=page_size,
        category=category,
    )
    return ExpenseListResponse(
        items=[ExpenseResponse.model_validate(e) for e in expenses],
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.post("", response_model=ExpenseResponse, status_code=HTTPStatus.CREATED)
async def create_expense(
    expense_data: ExpenseCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new expense."""
    service = ExpenseService(db)
    expense = await service.create(expense_data, current_user.id)
    return ExpenseResponse.model_validate(expense)


@router.get("/totals", response_model=ExpenseTotalsResponse)
async def get_expense_totals(
    current_user: CurrentUser,
    db: DBSession,
    company_id: int = Query(...),
):
    """Get expense totals for a company."""
    service = ExpenseService(db)
    return await service.get_totals(company_id)


@router.get("/{expense_id}", response_model=ExpenseResponse)
async def get_expense(
    expense_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get an expense by ID."""
    service = ExpenseService(db)
    expense = await service.get_by_id(expense_id)
    if not expense:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Expense not found")
    return ExpenseResponse.model_validate(expense)


@router.patch("/{expense_id}", response_model=ExpenseResponse)
async def update_expense(
    expense_id: int,
    expense_data: ExpenseUpdate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Update an expense."""
    service = ExpenseService(db)
    expense = await service.get_by_id(expense_id)
    if not expense:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Expense not found")
    expense = await service.update(expense, expense_data)
    return ExpenseResponse.model_validate(expense)


@router.delete("/{expense_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_expense(
    expense_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Delete an expense."""
    service = ExpenseService(db)
    expense = await service.get_by_id(expense_id)
    if not expense:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Expense not found")
    await service.delete(expense)


@router.post("/{expense_id}/receipt", response_model=ExpenseResponse)
async def upload_receipt(
    expense_id: int,
    file: UploadFile = File(...),
    current_user: CurrentUser = None,
    db: DBSession = None,
):
    """Upload a receipt for an expense (reuses attachments pattern)."""
    from src.attachments.service import AttachmentService

    service = ExpenseService(db)
    expense = await service.get_by_id(expense_id)
    if not expense:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Expense not found")

    attachment_service = AttachmentService(db)
    attachment = await attachment_service.upload_file(
        file=file,
        entity_type="expenses",
        entity_id=expense_id,
        user_id=current_user.id,
        category="receipt",
    )

    expense.receipt_attachment_id = attachment.id
    await db.flush()
    await db.refresh(expense)
    return ExpenseResponse.model_validate(expense)
