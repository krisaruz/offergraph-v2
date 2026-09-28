from fastapi import APIRouter

from app.adapters import get_registered_adapters
from app.runtime.report_runtime import ReportRuntime
from app.runtime.source_connection import SourceConnectionManager
from app.schemas.report import ReportRunResponse, SourceHealth, TargetBrief

router = APIRouter(prefix="/api/reports", tags=["reports"])
source_connections_router = APIRouter(
    prefix="/api/source-connections",
    tags=["source-connections"],
)


def _get_adapters():
    return get_registered_adapters()


@source_connections_router.get("/status", response_model=list[SourceHealth])
async def report_source_connection_status():
    manager = SourceConnectionManager(_get_adapters())
    return await manager.validate_required()


@router.post("", response_model=ReportRunResponse)
async def create_report(target: TargetBrief):
    runtime = ReportRuntime(_get_adapters())
    report_run = await runtime.run(target)
    return ReportRunResponse(reportRun=report_run)
