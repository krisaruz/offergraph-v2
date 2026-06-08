import json
import logging
import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.search_session import SearchSession
from app.models.tool_run import ToolRun

logger = logging.getLogger(__name__)


class TraceLogger:
    """
    运行轨迹记录器。
    负责将 SearchSession 和 ToolRun 持久化到数据库，
    使每次搜索的完整运行轨迹可审计。
    """

    def __init__(self, db: AsyncSession):
        self._db = db
        self._pending_runs: List[ToolRun] = []

    async def create_session(
        self,
        profile_snapshot: dict,
        user_id: Optional[str] = None,
        profile_id: Optional[str] = None,
    ) -> SearchSession:
        session = SearchSession(
            id=str(uuid.uuid4()),
            user_id=user_id,
            profile_id=profile_id,
            profile_snapshot_json=json.dumps(profile_snapshot, ensure_ascii=False),
            status="running",
        )
        self._db.add(session)
        await self._db.flush()
        return session

    async def update_session(
        self,
        session: SearchSession,
        *,
        status: Optional[str] = None,
        query_plan_json: Optional[str] = None,
        source_status_json: Optional[str] = None,
        cached_count: Optional[int] = None,
        fresh_count: Optional[int] = None,
        total_count: Optional[int] = None,
        search_duration_ms: Optional[int] = None,
        quality_report_json: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        if status is not None:
            session.status = status
        if query_plan_json is not None:
            session.query_plan_json = query_plan_json
        if source_status_json is not None:
            session.source_status_json = source_status_json
        if cached_count is not None:
            session.cached_count = cached_count
        if fresh_count is not None:
            session.fresh_count = fresh_count
        if total_count is not None:
            session.total_count = total_count
        if search_duration_ms is not None:
            session.search_duration_ms = search_duration_ms
        if quality_report_json is not None:
            session.quality_report_json = quality_report_json
        if error_message is not None:
            session.error_message = error_message
        session.updated_at = datetime.utcnow()
        await self._db.flush()

    async def log_tool_run(
        self,
        session_id: str,
        tool_name: str,
        tool_type: str,
        *,
        input_data: Optional[dict] = None,
        output_summary: Optional[dict] = None,
        status: str = "success",
        error_message: Optional[str] = None,
        started_at: Optional[datetime] = None,
        ended_at: Optional[datetime] = None,
        duration_ms: Optional[int] = None,
    ) -> ToolRun:
        run = ToolRun(
            id=str(uuid.uuid4()),
            session_id=session_id,
            tool_name=tool_name,
            tool_type=tool_type,
            input_json=json.dumps(input_data, ensure_ascii=False) if input_data else None,
            output_summary_json=json.dumps(output_summary, ensure_ascii=False) if output_summary else None,
            status=status,
            error_message=error_message,
            started_at=started_at or datetime.utcnow(),
            ended_at=ended_at or datetime.utcnow(),
            duration_ms=duration_ms,
        )
        self._db.add(run)
        await self._db.flush()
        return run

    async def flush_pending(self) -> None:
        """批量提交所有待写入的 tool_run 记录"""
        if self._pending_runs:
            self._db.add_all(self._pending_runs)
            await self._db.flush()
            self._pending_runs.clear()
