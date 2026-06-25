"""Role profile API routes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters import get_registered_adapters
from app.database import get_db
from app.schemas.role_profile import RoleProfileSearchRequest, RoleProfileSearchResponse
from app.services.role_profile_service import RoleProfileService

router = APIRouter(prefix="/api/role-profile", tags=["role-profile"])


@router.post("/search", response_model=RoleProfileSearchResponse)
async def role_profile_search(
    request: RoleProfileSearchRequest,
    db: AsyncSession = Depends(get_db),
):
    """Build a JD + interview evidence role profile from natural language keywords."""
    service = RoleProfileService(db=db, adapters=get_registered_adapters())
    return await service.search(
        keyword=request.keyword,
        identity=request.identity,
        regions=request.regions or [],
    )
