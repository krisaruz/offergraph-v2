"""公司面试画像 API"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.company_profile_service import CompanyProfileService

router = APIRouter(prefix="/api/company-profile", tags=["company-profile"])


@router.get("/{company}")
async def get_company_profile(
    company: str,
    position: Optional[str] = Query(None),
    candidate_type: Optional[str] = Query(None, alias="candidateType"),
    db: AsyncSession = Depends(get_db),
):
    """
    获取公司面试画像。
    只统计高可信真实问题，低质量数据不进入统计。
    """
    service = CompanyProfileService(db)
    return await service.get_company_profile(
        company=company,
        position=position,
        candidate_type=candidate_type,
    )
