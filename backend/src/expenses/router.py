"""Expense API routes.

All endpoints require that the caller can access the parent Company (owner
or admin/manager). Expense rows don't have their own `owner_id` column, so
access is derived from `Company.owner_id` via the linked `company_id`.
"""
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import select

from src.companies.models import Company
from src.core.constants import HTTPStatus
from src.core.data_scope import DataScope, get_data_scope
from src.core.router_utils import (
    CurrentUser,
    DBSession,
    calculate_pages,
    raise_forbidden,
)
from src.expenses.schemas import (
    ExpenseCreate,
    ExpenseListResponse,
    ExpenseResponse,
    ExpenseTotalsResponse,
    ExpenseUpdate,
)
from src.expenses.service import ExpenseService

router = APIRouter(prefix="/api/expenses", tags=["expenses"])


async def _require_company_access(db, company_id: int, data_scope: DataScope) -> Company:
    """Load the Company and ensure the caller can access it.

    Admin/manager/superuser bypass. Sales reps must own the company row.
    Raises 404 for missing, 403 for not-owner.
    """
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if company is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Company not found")
    if data_scope.can_see_all():
        return company
    if company.owner_id != data_scope.user_id:
        raise_forbidden("You do not have permission to access this company's expenses")
    return company


async def _load_expense_with_access(
    db,
    expense_id: int,
    data_scope: DataScope,
):
    """Fetch an expense and verify the caller can access the parent company.

    Raises 404 if the expense is missing or its parent company isn't
    accessible (we intentionally return 404 instead of 403 on cross-company
    reads to avoid leaking existence).
    """
    service = ExpenseService(db)
    expense = await service.get_by_id(expense_id)
    if expense is None:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Expense not found")
    if data_scope.can_see_all():
        return service, expense
    # Resolve the parent company to check ownership.
    result = await db.execute(select(Company).where(Company.id == expense.company_id))
    company = result.scalar_one_or_none()
    if company is None or company.owner_id != data_scope.user_id:
        # Don't reveal whether the expense exists cross-company.
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND, detail="Expense not found")
    return service, expense


@router.get("", response_model=ExpenseListResponse)
async def list_expenses(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    company_id: int = Query(...),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: str | None = None,
):
    """List expenses for a company."""
    await _require_company_access(db, company_id, data_scope)

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
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Create a new expense."""
    await _require_company_access(db, expense_data.company_id, data_scope)

    service = ExpenseService(db)
    expense = await service.create(expense_data, current_user.id)
    return ExpenseResponse.model_validate(expense)


@router.get("/totals", response_model=ExpenseTotalsResponse)
async def get_expense_totals(
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    company_id: int = Query(...),
):
    """Get expense totals for a company."""
    await _require_company_access(db, company_id, data_scope)

    service = ExpenseService(db)
    return await service.get_totals(company_id)


@router.get("/{expense_id}", response_model=ExpenseResponse)
async def get_expense(
    expense_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Get an expense by ID."""
    _, expense = await _load_expense_with_access(db, expense_id, data_scope)
    return ExpenseResponse.model_validate(expense)


@router.patch("/{expense_id}", response_model=ExpenseResponse)
async def update_expense(
    expense_id: int,
    expense_data: ExpenseUpdate,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Update an expense."""
    service, expense = await _load_expense_with_access(db, expense_id, data_scope)
    expense = await service.update(expense, expense_data)
    return ExpenseResponse.model_validate(expense)


@router.delete("/{expense_id}", status_code=HTTPStatus.NO_CONTENT)
async def delete_expense(
    expense_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
):
    """Delete an expense."""
    service, expense = await _load_expense_with_access(db, expense_id, data_scope)
    await service.delete(expense)


@router.post("/{expense_id}/receipt", response_model=ExpenseResponse)
async def upload_receipt(
    expense_id: int,
    current_user: CurrentUser,
    db: DBSession,
    data_scope: Annotated[DataScope, Depends(get_data_scope)],
    file: UploadFile = File(...),
):
    """Upload a receipt for an expense (reuses attachments pattern)."""
    from src.attachments.service import AttachmentService

    service, expense = await _load_expense_with_access(db, expense_id, data_scope)

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
