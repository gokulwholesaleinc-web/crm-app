"""Expense service layer."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.constants import DEFAULT_PAGE_SIZE
from src.expenses.models import Expense


class ExpenseService:
    """Service for Expense CRUD operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, expense_id: int) -> Expense | None:
        result = await self.db.execute(
            select(Expense).where(Expense.id == expense_id)
        )
        return result.scalar_one_or_none()

    async def get_list(
        self,
        company_id: int,
        page: int = 1,
        page_size: int = DEFAULT_PAGE_SIZE,
        category: str | None = None,
    ) -> tuple[list[Expense], int]:
        query = select(Expense).where(Expense.company_id == company_id)
        if category:
            query = query.where(Expense.category == category)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await self.db.execute(count_query)
        total = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query = query.order_by(Expense.expense_date.desc()).offset(offset).limit(page_size)
        result = await self.db.execute(query)
        items = list(result.scalars().all())
        return items, total

    async def create(self, data, user_id: int) -> Expense:
        expense = Expense(
            company_id=data.company_id,
            amount=data.amount,
            currency=data.currency,
            description=data.description,
            expense_date=data.expense_date,
            category=data.category,
            receipt_attachment_id=data.receipt_attachment_id,
            payment_id=data.payment_id,
            created_by_id=user_id,
        )
        self.db.add(expense)
        await self.db.flush()
        await self.db.refresh(expense)
        return expense

    async def update(self, expense: Expense, data) -> Expense:
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(expense, field, value)
        await self.db.flush()
        await self.db.refresh(expense)
        return expense

    async def delete(self, expense: Expense) -> None:
        await self.db.delete(expense)
        await self.db.flush()

    async def get_totals(self, company_id: int) -> dict:
        """Get expense totals and breakdown by category."""
        result = await self.db.execute(
            select(
                func.coalesce(func.sum(Expense.amount), 0).label("total"),
                func.count(Expense.id).label("count"),
            ).where(Expense.company_id == company_id)
        )
        row = result.one()
        total_amount = float(row.total)
        count = row.count

        # Category breakdown
        cat_result = await self.db.execute(
            select(
                func.coalesce(Expense.category, "Uncategorized").label("cat"),
                func.sum(Expense.amount).label("cat_total"),
            )
            .where(Expense.company_id == company_id)
            .group_by(Expense.category)
        )
        by_category = {r.cat: float(r.cat_total) for r in cat_result.all()}

        return {
            "total_amount": total_amount,
            "currency": "USD",
            "count": count,
            "by_category": by_category,
        }
