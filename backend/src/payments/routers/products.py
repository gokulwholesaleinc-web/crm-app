"""Product endpoints sub-router."""

import logging

from fastapi import APIRouter, Query

from src.core.constants import HTTPStatus
from src.core.router_utils import CurrentUser, DBSession, calculate_pages
from src.payments.schemas import (
    ProductCreate,
    ProductListResponse,
    ProductResponse,
)
from src.payments.service import ProductService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/products", response_model=ProductListResponse)
async def list_products(
    current_user: CurrentUser,
    db: DBSession,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    is_active: bool | None = None,
):
    """List products."""
    service = ProductService(db)
    products, total = await service.get_list(
        page=page,
        page_size=page_size,
        is_active=is_active,
    )

    return ProductListResponse(
        items=[ProductResponse.model_validate(p) for p in products],
        total=total,
        page=page,
        page_size=page_size,
        pages=calculate_pages(total, page_size),
    )


@router.post("/products", response_model=ProductResponse, status_code=HTTPStatus.CREATED)
async def create_product(
    product_data: ProductCreate,
    current_user: CurrentUser,
    db: DBSession,
):
    """Create a new product."""
    service = ProductService(db)
    product = await service.create(product_data, current_user.id)
    return ProductResponse.model_validate(product)
