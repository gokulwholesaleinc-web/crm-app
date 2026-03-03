"""Meta integration API routes."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from src.core.router_utils import DBSession, CurrentUser
from src.meta.schemas import MetaSyncRequest, CompanyMetaDataResponse
from src.meta.service import MetaService

router = APIRouter(prefix="/api/meta", tags=["meta"])


@router.get("/companies/{company_id}", response_model=CompanyMetaDataResponse)
async def get_company_meta(
    company_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Get Meta data for a company."""
    service = MetaService(db)
    meta = await service.get_by_company(company_id)
    if not meta:
        raise HTTPException(status_code=404, detail="No Meta data found for this company")
    return CompanyMetaDataResponse.model_validate(meta)


@router.post("/companies/{company_id}/sync", response_model=CompanyMetaDataResponse)
async def sync_company_meta(
    company_id: int,
    request_data: MetaSyncRequest,
    current_user: CurrentUser,
    db: DBSession,
):
    """Sync Meta page data for a company."""
    service = MetaService(db)
    meta = await service.sync_page(company_id, request_data.page_id)
    return CompanyMetaDataResponse.model_validate(meta)


@router.get("/companies/{company_id}/export-csv")
async def export_meta_csv(
    company_id: int,
    current_user: CurrentUser,
    db: DBSession,
):
    """Export Meta data as CSV."""
    service = MetaService(db)
    csv_content = await service.export_csv(company_id)
    if not csv_content:
        raise HTTPException(status_code=404, detail="No Meta data to export")
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=meta-company-{company_id}.csv"},
    )
