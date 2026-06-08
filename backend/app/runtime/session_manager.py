import json
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.search_session import SearchSession
from app.runtime.trace_logger import TraceLogger

logger = logging.getLogger(__name__)


class SessionManager:
    """
    搜索会话管理器。
    负责创建、更新、查询 SearchSession。
    """

    def __init__(self, db: AsyncSession):
        self._db = db
        self._trace = TraceLogger(db)

    async def create_session(
        self,
        profile_snapshot: dict,
        user_id: Optional[str] = None,
        profile_id: Optional[str] = None,
    ) -> SearchSession:
        return await self._trace.create_session(
            profile_snapshot=profile_snapshot,
            user_id=user_id,
            profile_id=profile_id,
        )

    async def mark_success(
        self,
        session: SearchSession,
        *,
        cached_count: int = 0,
        fresh_count: int = 0,
        total_count: int = 0,
        search_duration_ms: int = 0,
        source_status: Optional[dict] = None,
        quality_report: Optional[dict] = None,
    ) -> None:
        await self._trace.update_session(
            session,
            status="success",
            cached_count=cached_count,
            fresh_count=fresh_count,
            total_count=total_count,
            search_duration_ms=search_duration_ms,
            source_status_json=json.dumps(source_status, ensure_ascii=False) if source_status else None,
            quality_report_json=json.dumps(quality_report, ensure_ascii=False) if quality_report else None,
        )

    async def mark_partial_success(
        self,
        session: SearchSession,
        *,
        cached_count: int = 0,
        fresh_count: int = 0,
        total_count: int = 0,
        search_duration_ms: int = 0,
        source_status: Optional[dict] = None,
        quality_report: Optional[dict] = None,
    ) -> None:
        await self._trace.update_session(
            session,
            status="partial_success",
            cached_count=cached_count,
            fresh_count=fresh_count,
            total_count=total_count,
            search_duration_ms=search_duration_ms,
            source_status_json=json.dumps(source_status, ensure_ascii=False) if source_status else None,
            quality_report_json=json.dumps(quality_report, ensure_ascii=False) if quality_report else None,
        )

    async def mark_failed(
        self,
        session: SearchSession,
        error_message: str,
        search_duration_ms: int = 0,
        source_status: Optional[dict] = None,
    ) -> None:
        await self._trace.update_session(
            session,
            status="failed",
            error_message=error_message,
            search_duration_ms=search_duration_ms,
            source_status_json=json.dumps(source_status, ensure_ascii=False) if source_status else None,
        )

    async def set_query_plan(self, session: SearchSession, query_plan: dict) -> None:
        await self._trace.update_session(
            session,
            query_plan_json=json.dumps(query_plan, ensure_ascii=False),
        )
