import asyncio
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import SourceAdapter, SourceQuery, SourceSearchResult
from app.config import settings
from app.models.source_document import SourceDocumentModel
from app.runtime.hook_engine import HookEngine, HookType, create_default_hook_engine
from app.runtime.permission_guard import PermissionGuard
from app.runtime.query_planner import QueryPlanner, QueryPlan
from app.runtime.ranker import Ranker
from app.runtime.session_manager import SessionManager
from app.runtime.tool_registry import ToolRegistry
from app.runtime.trace_logger import TraceLogger

logger = logging.getLogger(__name__)


class AgentRuntime:
    """
    面试情报 Agent Runtime。
    统一编排 Query Planning → Source Search → Permission Check → Hook → Result。
    Phase 1 实现：创建 session、记录 tool_run、并发搜索、单源容错。
    """

    def __init__(
        self,
        db: AsyncSession,
        adapters: Dict[str, SourceAdapter],
        tool_registry: Optional[ToolRegistry] = None,
        permission_guard: Optional[PermissionGuard] = None,
        hook_engine: Optional[HookEngine] = None,
    ):
        self._db = db
        self._adapters = adapters
        self._tool_registry = tool_registry or ToolRegistry()
        self._permission_guard = permission_guard or PermissionGuard()
        self._hook_engine = hook_engine or create_default_hook_engine()
        self._query_planner = QueryPlanner()
        self._session_manager = SessionManager(db)
        self._trace = TraceLogger(db)
        self._ranker = Ranker()

    async def run_search(self, profile: dict) -> Dict[str, Any]:
        """
        执行一次完整的面试情报搜索。
        
        流程：
        1. 创建 SearchSession
        2. QueryPlanner 生成 QueryPlan
        3. PRE_SEARCH hook
        4. 并发调用 SourceAdapters（每个 source 独立 timeout，单源失败不影响整体）
        5. POST_SEARCH hook
        6. 去重
        7. 返回结果并更新 session 状态
        """
        start_time = time.time()

        # 1. 创建 SearchSession
        session = await self._session_manager.create_session(
            profile_snapshot=profile,
            user_id=profile.get("user_id"),
            profile_id=profile.get("id"),
        )

        try:
            # 2. QueryPlanner 生成 QueryPlan
            query_plan = self._query_planner.plan(profile)
            await self._session_manager.set_query_plan(
                session, query_plan.model_dump()
            )

            # 3. PRE_SEARCH hook
            hook_result = await self._hook_engine.run_hooks(
                HookType.PRE_SEARCH,
                {"queries": [q.model_dump() for q in query_plan.queries]},
            )
            if not hook_result.passed:
                await self._session_manager.mark_failed(
                    session,
                    error_message=f"PRE_SEARCH hook blocked: {hook_result.blocked_reason}",
                    search_duration_ms=self._elapsed_ms(start_time),
                )
                await self._db.commit()
                return self._build_error_response(session.id, hook_result.blocked_reason)

            # 4. 并发调用 SourceAdapters
            source_status: Dict[str, str] = {}
            all_results: List[Dict[str, Any]] = []

            search_tasks = []
            for adapter_id, adapter in self._adapters.items():
                perm = self._permission_guard.can_search_source(adapter_id)
                if not perm.allowed:
                    source_status[adapter_id] = f"blocked:{perm.policy.value}"
                    continue
                search_tasks.append(
                    self._search_single_source(
                        session.id, adapter, query_plan, source_status
                    )
                )

            if search_tasks:
                task_results = await asyncio.gather(*search_tasks, return_exceptions=True)
                for result in task_results:
                    if isinstance(result, Exception):
                        logger.warning(f"Source search exception: {result}")
                        continue
                    if isinstance(result, list):
                        all_results.extend(result)

            # 5. POST_SEARCH hook
            await self._hook_engine.run_hooks(
                HookType.POST_SEARCH,
                {"results": all_results},
            )

            # 6. 去重（基于 source_url）
            seen_urls = set()
            deduped_results = []
            for item in all_results:
                url = item.get("source_url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    deduped_results.append(item)

            # 6.5 WebFetch: 抓取允许抓取的 Top URL 并写入 source_documents
            fetchable_urls = []
            for item in deduped_results[:settings.webfetch_max_urls]:
                url = item.get("source_url", "")
                source = item.get("source", "")
                perm = self._permission_guard.can_fetch_url(url, source)
                if perm.allowed:
                    fetchable_urls.append(item)
                else:
                    item["has_full_text"] = False
                    item["fetch_policy"] = perm.policy.value

            fetched_doc_ids = await self._batch_fetch(session.id, fetchable_urls)

            # 6.6 LLM 抽取：启动后台任务，不阻塞搜索结果返回
            if fetched_doc_ids:
                asyncio.create_task(
                    self._safe_batch_extract(session.id, fetched_doc_ids)
                )

            # 7. Ranker 排序（内置过滤过期内容）
            url_counts: Dict[str, int] = {}
            for item in all_results:
                u = item.get("source_url", "")
                url_counts[u] = url_counts.get(u, 0) + 1

            ranked_results = self._ranker.rank(deduped_results, url_counts, profile=profile)
            ranked_results = ranked_results[:settings.ranking_top_n]

            # 8. 更新 session 状态
            duration_ms = self._elapsed_ms(start_time)
            total_count = len(ranked_results)

            has_success = any(s == "ok" for s in source_status.values())
            has_failure = any(s != "ok" for s in source_status.values())

            if not has_success:
                await self._session_manager.mark_failed(
                    session,
                    error_message="All sources failed",
                    search_duration_ms=duration_ms,
                    source_status=source_status,
                )
                status = "failed"
            elif has_failure:
                await self._session_manager.mark_partial_success(
                    session,
                    fresh_count=total_count,
                    total_count=total_count,
                    search_duration_ms=duration_ms,
                    source_status=source_status,
                )
                status = "partial_success"
            else:
                await self._session_manager.mark_success(
                    session,
                    fresh_count=total_count,
                    total_count=total_count,
                    search_duration_ms=duration_ms,
                    source_status=source_status,
                )
                status = "success"

            await self._db.commit()

            return {
                "sessionId": session.id,
                "status": status,
                "items": ranked_results,
                "total": total_count,
                "sourcesStatus": source_status,
                "cachedCount": 0,
                "freshCount": total_count,
                "searchDuration": duration_ms,
                "qualityReport": {
                    "filteredCount": len(all_results) - len(deduped_results),
                    "duplicateCount": len(all_results) - len(deduped_results),
                    "hookWarnings": hook_result.warnings,
                    "fetchedCount": len(fetched_doc_ids),
                },
            }

        except Exception as e:
            logger.exception(f"AgentRuntime.run_search failed: {e}")
            duration_ms = self._elapsed_ms(start_time)
            await self._session_manager.mark_failed(
                session,
                error_message=str(e),
                search_duration_ms=duration_ms,
            )
            await self._db.commit()
            return self._build_error_response(session.id, str(e))

    async def _search_single_source(
        self,
        session_id: str,
        adapter: SourceAdapter,
        query_plan: QueryPlan,
        source_status: Dict[str, str],
    ) -> List[Dict[str, Any]]:
        """搜索单个来源，独立 timeout，记录 tool_run"""
        adapter_id = adapter.id
        timeout = settings.search_timeout_platform
        results: List[Dict[str, Any]] = []
        started_at = datetime.utcnow()

        max_queries_per_source = 2

        try:
            queries_to_run = query_plan.queries[:max_queries_per_source]

            async def _run_one_query(planned_query):
                source_query = SourceQuery(
                    query=planned_query.query,
                    company=planned_query.company,
                    position=planned_query.position,
                    candidate_type=planned_query.candidate_type,
                    region=planned_query.region,
                    limit=query_plan.max_results_per_query,
                )
                return await asyncio.wait_for(
                    adapter.search(source_query),
                    timeout=timeout,
                )

            query_tasks = [_run_one_query(q) for q in queries_to_run]
            query_results = await asyncio.gather(*query_tasks, return_exceptions=True)

            for qr in query_results:
                if isinstance(qr, Exception):
                    logger.warning(f"Query failed for {adapter_id}: {qr}")
                    continue
                for sr in qr:
                    results.append({
                        "source": sr.source,
                        "source_url": sr.source_url,
                        "title": sr.title,
                        "snippet": sr.snippet,
                        "published_at": sr.published_at,
                    })

            source_status[adapter_id] = "ok"
            ended_at = datetime.utcnow()
            duration_ms = int((ended_at - started_at).total_seconds() * 1000)

            await self._trace.log_tool_run(
                session_id=session_id,
                tool_name=f"search_{adapter_id}",
                tool_type="search",
                input_data={"query_count": len(queries_to_run), "adapter": adapter_id},
                output_summary={"result_count": len(results)},
                status="success",
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
            )

        except asyncio.TimeoutError:
            source_status[adapter_id] = "timeout"
            ended_at = datetime.utcnow()
            duration_ms = int((ended_at - started_at).total_seconds() * 1000)

            await self._trace.log_tool_run(
                session_id=session_id,
                tool_name=f"search_{adapter_id}",
                tool_type="search",
                input_data={"adapter": adapter_id},
                status="timeout",
                error_message=f"Timeout after {timeout}s",
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
            )

        except Exception as e:
            source_status[adapter_id] = f"error:{type(e).__name__}"
            ended_at = datetime.utcnow()
            duration_ms = int((ended_at - started_at).total_seconds() * 1000)

            await self._trace.log_tool_run(
                session_id=session_id,
                tool_name=f"search_{adapter_id}",
                tool_type="search",
                input_data={"adapter": adapter_id},
                status="error",
                error_message=str(e),
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
            )

        return results

    async def _batch_fetch(
        self,
        session_id: str,
        items: List[Dict[str, Any]],
    ) -> List[str]:
        """批量并行抓取 URL，写入 source_documents，返回成功的 doc id 列表"""
        if not items:
            return []

        # 预查询已存在的 URL（批量查重，避免逐个查询）
        from sqlalchemy import select as sa_select
        urls = [item.get("source_url", "") for item in items]
        existing_stmt = sa_select(SourceDocumentModel).where(
            SourceDocumentModel.source_url.in_(urls)
        )
        existing_result = await self._db.execute(existing_stmt)
        existing_docs = {doc.source_url: doc for doc in existing_result.scalars().all()}

        # 并行抓取任务
        async def _fetch_one(item: Dict[str, Any]) -> Optional[str]:
            url = item.get("source_url", "")
            source = item.get("source", "search_engine")
            started_at = datetime.utcnow()

            try:
                # 如果已存在，直接复用
                if url in existing_docs:
                    existing_doc = existing_docs[url]
                    item["has_full_text"] = True
                    item["source_document_id"] = existing_doc.id
                    return existing_doc.id

                # 抓取内容
                adapter = self._adapters.get(source)
                doc = None
                if adapter and hasattr(adapter, "fetch"):
                    doc = await asyncio.wait_for(
                        adapter.fetch(url),
                        timeout=settings.webfetch_timeout,
                    )

                if not doc and "search_engine" in self._adapters:
                    doc = await asyncio.wait_for(
                        self._adapters["search_engine"].fetch(url),
                        timeout=settings.webfetch_timeout,
                    )

                if not doc or not doc.full_text:
                    item["has_full_text"] = False
                    return None

                # 写入数据库
                source_doc = SourceDocumentModel(
                    id=str(uuid.uuid4()),
                    source=doc.source,
                    source_url=doc.source_url,
                    title=doc.title,
                    snippet=doc.snippet,
                    full_text=doc.full_text,
                    content_hash=doc.content_hash,
                    fetched_at=datetime.utcnow(),
                    fetch_policy="public_fetch_allowed",
                    extraction_status="pending",
                )
                self._db.add(source_doc)
                await self._db.flush()

                item["has_full_text"] = True
                item["source_document_id"] = source_doc.id

                ended_at = datetime.utcnow()
                await self._trace.log_tool_run(
                    session_id=session_id,
                    tool_name="fetch_web",
                    tool_type="fetch",
                    input_data={"url": url, "source": source},
                    output_summary={"doc_id": source_doc.id, "text_len": len(doc.full_text)},
                    status="success",
                    started_at=started_at,
                    ended_at=ended_at,
                    duration_ms=int((ended_at - started_at).total_seconds() * 1000),
                )

                return source_doc.id

            except asyncio.TimeoutError:
                item["has_full_text"] = False
                return None
            except Exception as e:
                item["has_full_text"] = False
                logger.warning(f"Fetch failed for {url}: {e}")
                return None

        # 并行执行所有抓取任务
        tasks = [_fetch_one(item) for item in items]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        doc_ids = []
        for result in results:
            if isinstance(result, str):
                doc_ids.append(result)

        return doc_ids

    async def _batch_extract(self, session_id: str, doc_ids: List[str]) -> None:
        """批量 LLM 抽取，每个 doc 独立 db session，并行执行"""
        if not doc_ids:
            return

        tasks = [
            self._extract_single_doc_with_trace(session_id, doc_id)
            for doc_id in doc_ids
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _extract_single_doc_with_trace(self, session_id: str, doc_id: str) -> None:
        """单篇 LLM 抽取 + trace 记录，独立 db session"""
        from app.database import async_session_factory
        from app.llm.structured_extract import extract_interview
        from sqlalchemy import select

        started_at = datetime.utcnow()
        try:
            async with async_session_factory() as db:
                stmt = select(SourceDocumentModel).where(SourceDocumentModel.id == doc_id)
                result = await db.execute(stmt)
                source_doc = result.scalar_one_or_none()
                if not source_doc:
                    return

                extract_result = await extract_interview(db=db, source_doc=source_doc)
                await db.commit()

                ended_at = datetime.utcnow()
                trace = TraceLogger(db)
                await trace.log_tool_run(
                    session_id=session_id,
                    tool_name="extract_interview",
                    tool_type="extract",
                    input_data={"source_document_id": doc_id},
                    output_summary=extract_result,
                    status="success" if extract_result.get("status") == "extracted" else "error",
                    started_at=started_at,
                    ended_at=ended_at,
                    duration_ms=int((ended_at - started_at).total_seconds() * 1000),
                )
                await db.commit()
        except Exception as e:
            logger.warning(f"Extraction failed for doc {doc_id}: {e}")

    async def _safe_batch_extract(self, session_id: str, doc_ids: List[str]) -> None:
        """后台 LLM 提取任务，每个 doc 独立 db session，全部并行执行"""
        tasks = [
            self._extract_single_doc(session_id, doc_id)
            for doc_id in doc_ids
        ]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _extract_single_doc(self, session_id: str, doc_id: str) -> None:
        """单篇 LLM 抽取，使用独立 db session"""
        from app.database import async_session_factory
        from app.llm.structured_extract import extract_interview
        from sqlalchemy import select

        started_at = datetime.utcnow()
        try:
            async with async_session_factory() as db:
                stmt = select(SourceDocumentModel).where(SourceDocumentModel.id == doc_id)
                result = await db.execute(stmt)
                source_doc = result.scalar_one_or_none()
                if not source_doc:
                    return

                extract_result = await extract_interview(db=db, source_doc=source_doc)
                await db.commit()

                logger.info(
                    f"Background extract done: doc={doc_id} "
                    f"status={extract_result.get('status')}"
                )
        except Exception as e:
            logger.warning(f"Background extraction failed for doc {doc_id}: {e}")

    def _elapsed_ms(self, start_time: float) -> int:
        return int((time.time() - start_time) * 1000)

    def _build_error_response(self, session_id: str, error: Optional[str]) -> Dict[str, Any]:
        return {
            "sessionId": session_id,
            "status": "failed",
            "items": [],
            "total": 0,
            "sourcesStatus": {},
            "cachedCount": 0,
            "freshCount": 0,
            "searchDuration": 0,
            "error": error,
        }
