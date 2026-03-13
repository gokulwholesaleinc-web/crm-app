"""Tests for Expenses API.

Tests cover:
- Create expense
- List expenses with pagination and category filter
- Get expense totals
- Get single expense
- Update expense
- Delete expense
- Upload receipt
- Tests do NOT mock anything.
"""

import io

import pytest


class TestCreateExpense:
    """Test POST /api/expenses."""

    @pytest.mark.asyncio
    async def test_create_expense(self, client, auth_headers, test_company):
        """Should create a new expense."""
        response = await client.post(
            "/api/expenses",
            json={
                "company_id": test_company.id,
                "amount": 150.50,
                "currency": "USD",
                "description": "Office supplies",
                "expense_date": "2026-01-15",
                "category": "Supplies",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["company_id"] == test_company.id
        assert data["amount"] == 150.50
        assert data["currency"] == "USD"
        assert data["description"] == "Office supplies"
        assert data["expense_date"] == "2026-01-15"
        assert data["category"] == "Supplies"
        assert data["created_by_id"] is not None
        assert data["id"] is not None

    @pytest.mark.asyncio
    async def test_create_expense_defaults_currency_to_usd(self, client, auth_headers, test_company):
        """Should default currency to USD."""
        response = await client.post(
            "/api/expenses",
            json={
                "company_id": test_company.id,
                "amount": 99.99,
                "description": "Travel expense",
                "expense_date": "2026-02-01",
            },
            headers=auth_headers,
        )
        assert response.status_code == 201
        assert response.json()["currency"] == "USD"

    @pytest.mark.asyncio
    async def test_create_expense_requires_auth(self, client, test_company):
        """Should return 401 without auth headers."""
        response = await client.post(
            "/api/expenses",
            json={
                "company_id": test_company.id,
                "amount": 50.0,
                "description": "Test",
                "expense_date": "2026-01-01",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_expense_validates_required_fields(self, client, auth_headers):
        """Should return 422 for missing required fields."""
        response = await client.post(
            "/api/expenses",
            json={},
            headers=auth_headers,
        )
        assert response.status_code == 422


class TestListExpenses:
    """Test GET /api/expenses."""

    @pytest.mark.asyncio
    async def test_list_expenses_empty(self, client, auth_headers, test_company):
        """Should return empty list when no expenses exist."""
        response = await client.get(
            f"/api/expenses?company_id={test_company.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["items"] == []
        assert data["total"] == 0
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_expenses_with_data(self, client, auth_headers, test_company):
        """Should return expenses for a company."""
        # Create two expenses
        for i in range(2):
            await client.post(
                "/api/expenses",
                json={
                    "company_id": test_company.id,
                    "amount": 100.0 * (i + 1),
                    "description": f"Expense {i + 1}",
                    "expense_date": f"2026-01-{10 + i:02d}",
                },
                headers=auth_headers,
            )

        response = await client.get(
            f"/api/expenses?company_id={test_company.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        assert len(data["items"]) == 2

    @pytest.mark.asyncio
    async def test_list_expenses_filter_by_category(self, client, auth_headers, test_company):
        """Should filter expenses by category."""
        # Create expenses with different categories
        await client.post(
            "/api/expenses",
            json={
                "company_id": test_company.id,
                "amount": 50.0,
                "description": "Travel",
                "expense_date": "2026-01-01",
                "category": "Travel",
            },
            headers=auth_headers,
        )
        await client.post(
            "/api/expenses",
            json={
                "company_id": test_company.id,
                "amount": 30.0,
                "description": "Lunch",
                "expense_date": "2026-01-02",
                "category": "Food",
            },
            headers=auth_headers,
        )

        response = await client.get(
            f"/api/expenses?company_id={test_company.id}&category=Travel",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["items"][0]["category"] == "Travel"

    @pytest.mark.asyncio
    async def test_list_expenses_pagination(self, client, auth_headers, test_company):
        """Should paginate expenses."""
        for i in range(3):
            await client.post(
                "/api/expenses",
                json={
                    "company_id": test_company.id,
                    "amount": 10.0,
                    "description": f"Expense {i}",
                    "expense_date": f"2026-01-{i + 1:02d}",
                },
                headers=auth_headers,
            )

        response = await client.get(
            f"/api/expenses?company_id={test_company.id}&page=1&page_size=2",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert len(data["items"]) == 2
        assert data["pages"] == 2


class TestGetExpenseTotals:
    """Test GET /api/expenses/totals."""

    @pytest.mark.asyncio
    async def test_totals_empty(self, client, auth_headers, test_company):
        """Should return zero totals when no expenses."""
        response = await client.get(
            f"/api/expenses/totals?company_id={test_company.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_amount"] == 0.0
        assert data["count"] == 0
        assert data["by_category"] == {}

    @pytest.mark.asyncio
    async def test_totals_with_data(self, client, auth_headers, test_company):
        """Should return correct totals and category breakdown."""
        await client.post(
            "/api/expenses",
            json={
                "company_id": test_company.id,
                "amount": 100.0,
                "description": "Travel",
                "expense_date": "2026-01-01",
                "category": "Travel",
            },
            headers=auth_headers,
        )
        await client.post(
            "/api/expenses",
            json={
                "company_id": test_company.id,
                "amount": 50.0,
                "description": "More Travel",
                "expense_date": "2026-01-02",
                "category": "Travel",
            },
            headers=auth_headers,
        )
        await client.post(
            "/api/expenses",
            json={
                "company_id": test_company.id,
                "amount": 25.0,
                "description": "Lunch",
                "expense_date": "2026-01-03",
                "category": "Food",
            },
            headers=auth_headers,
        )

        response = await client.get(
            f"/api/expenses/totals?company_id={test_company.id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["total_amount"] == 175.0
        assert data["count"] == 3
        assert data["by_category"]["Travel"] == 150.0
        assert data["by_category"]["Food"] == 25.0


class TestUpdateExpense:
    """Test PATCH /api/expenses/{expense_id}."""

    @pytest.mark.asyncio
    async def test_update_expense(self, client, auth_headers, test_company):
        """Should update an expense."""
        create_resp = await client.post(
            "/api/expenses",
            json={
                "company_id": test_company.id,
                "amount": 100.0,
                "description": "Original",
                "expense_date": "2026-01-01",
            },
            headers=auth_headers,
        )
        expense_id = create_resp.json()["id"]

        response = await client.patch(
            f"/api/expenses/{expense_id}",
            json={"amount": 200.0, "description": "Updated"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["amount"] == 200.0
        assert data["description"] == "Updated"

    @pytest.mark.asyncio
    async def test_update_expense_not_found(self, client, auth_headers):
        """Should return 404 for non-existent expense."""
        response = await client.patch(
            "/api/expenses/99999",
            json={"amount": 200.0},
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_partial_update(self, client, auth_headers, test_company):
        """Should only update provided fields."""
        create_resp = await client.post(
            "/api/expenses",
            json={
                "company_id": test_company.id,
                "amount": 100.0,
                "description": "Original desc",
                "expense_date": "2026-01-01",
                "category": "Travel",
            },
            headers=auth_headers,
        )
        expense_id = create_resp.json()["id"]

        response = await client.patch(
            f"/api/expenses/{expense_id}",
            json={"category": "Food"},
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["category"] == "Food"
        assert data["amount"] == 100.0
        assert data["description"] == "Original desc"


class TestDeleteExpense:
    """Test DELETE /api/expenses/{expense_id}."""

    @pytest.mark.asyncio
    async def test_delete_expense(self, client, auth_headers, test_company):
        """Should delete an expense."""
        create_resp = await client.post(
            "/api/expenses",
            json={
                "company_id": test_company.id,
                "amount": 100.0,
                "description": "To delete",
                "expense_date": "2026-01-01",
            },
            headers=auth_headers,
        )
        expense_id = create_resp.json()["id"]

        response = await client.delete(
            f"/api/expenses/{expense_id}",
            headers=auth_headers,
        )
        assert response.status_code == 204

        # Verify it's gone
        get_resp = await client.get(
            f"/api/expenses/{expense_id}",
            headers=auth_headers,
        )
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_expense_not_found(self, client, auth_headers):
        """Should return 404 for non-existent expense."""
        response = await client.delete(
            "/api/expenses/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestGetExpense:
    """Test GET /api/expenses/{expense_id}."""

    @pytest.mark.asyncio
    async def test_get_expense(self, client, auth_headers, test_company):
        """Should return a single expense by ID."""
        create_resp = await client.post(
            "/api/expenses",
            json={
                "company_id": test_company.id,
                "amount": 75.0,
                "description": "Get test",
                "expense_date": "2026-03-01",
                "category": "Supplies",
            },
            headers=auth_headers,
        )
        expense_id = create_resp.json()["id"]

        response = await client.get(
            f"/api/expenses/{expense_id}",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == expense_id
        assert data["amount"] == 75.0
        assert data["description"] == "Get test"

    @pytest.mark.asyncio
    async def test_get_expense_not_found(self, client, auth_headers):
        """Should return 404 for non-existent expense."""
        response = await client.get(
            "/api/expenses/99999",
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestUploadReceipt:
    """Test POST /api/expenses/{expense_id}/receipt."""

    @pytest.mark.asyncio
    async def test_upload_receipt(self, client, auth_headers, test_company):
        """Should upload a receipt and link it to the expense."""
        create_resp = await client.post(
            "/api/expenses",
            json={
                "company_id": test_company.id,
                "amount": 45.00,
                "description": "Lunch receipt",
                "expense_date": "2026-02-15",
                "category": "Food",
            },
            headers=auth_headers,
        )
        assert create_resp.status_code == 201
        expense_id = create_resp.json()["id"]
        assert create_resp.json()["receipt_attachment_id"] is None

        file_content = b"fake receipt image data"
        response = await client.post(
            f"/api/expenses/{expense_id}/receipt",
            headers=auth_headers,
            files={"file": ("receipt.png", io.BytesIO(file_content), "image/png")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == expense_id
        assert data["receipt_attachment_id"] is not None

    @pytest.mark.asyncio
    async def test_upload_receipt_not_found(self, client, auth_headers):
        """Should return 404 for non-existent expense."""
        file_content = b"fake receipt"
        response = await client.post(
            "/api/expenses/99999/receipt",
            headers=auth_headers,
            files={"file": ("receipt.png", io.BytesIO(file_content), "image/png")},
        )
        assert response.status_code == 404
