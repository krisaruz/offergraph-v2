"""
StreamingCoordinator — 流式搜索协调器。

将搜索流程拆分为"搜索阶段"和"增强阶段"：
- 搜索阶段（快速）：规划 → 多源搜索 → 排序 → search_completed  (~2-3秒)
- 增强阶段（后台）：网页抓取 → LLM 结构化抽取 → enhance_completed

前端在 search_completed 后即可停止计时、展示结果；
增强阶段的进度通过 activity_log / enhance_progress 实时推送，
完成后卡片上出现"已分析"徽章，用户无感增强。

SSE 事件流：
  session_created → activity_log → query_plan_ready
  → [search_started → source_results → source_completed]...
  → ranking_completed → search_completed
  → enhance_start → [fetch_completed / extract_completed / enhance_progress]...
  → enhance_completed → stream_end
"""

import asyncio
import json
import logging
import re
import time
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Dict, List, Optional

from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import SourceAdapter, SourceQuery, SourceSearchItem, SourceSearchResult, SourceStatus
from app.config import settings
from app.database import async_session_factory
from app.models.source_document import SourceDocumentModel
from app.runtime.hook_engine import HookEngine, HookType, create_default_hook_engine
from app.runtime.permission_guard import PermissionGuard
from app.runtime.query_planner import QueryPlanner
from app.runtime.ranker import Ranker
from app.runtime.session_manager import SessionManager
from app.runtime.source_health import SourceHealthRegistry
from app.runtime.tool_registry import ToolRegistry
from app.runtime.trace_logger import TraceLogger

logger = logging.getLogger(__name__)

SSE_ID_LEN = 8
EXTRACT_TIMEOUT_S = 90


def _sse_id() -> str:
    return uuid.uuid4().hex[:SSE_ID_LEN]


class StreamingCoordinator:
    """
    流式协调器：管理 asyncio.Queue 事件总线，编排 Agent Tasks。

    用法:
        coordinator = StreamingCoordinator(db, adapters)
        async for sse_chunk in coordinator.run_stream(profile):
            yield sse_chunk  # SSE 格式字符串
    """

    def __init__(
        self,
        db: AsyncSession,
        adapters: Dict[str, SourceAdapter],
        tool_registry: Optional[ToolRegistry] = None,
        permission_guard: Optional[PermissionGuard] = None,
        hook_engine: Optional[HookEngine] = None,
        source_health_registry: Optional[SourceHealthRegistry] = None,
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
        self._source_health = source_health_registry or SourceHealthRegistry()

    async def run_stream(self, profile: dict) -> AsyncGenerator[str, None]:
        """
        执行一次流式搜索，产出 SSE 格式字符串。
        搜索阶段完成后立即发出 search_completed，随后进入增强阶段。
        """
        start_time = time.time()
        queue: asyncio.Queue[Optional[dict]] = asyncio.Queue(maxsize=500)
        active_tasks: List[asyncio.Task] = []

        def _push(event_type: str, data: dict):
            """安全推送事件到队列"""
            data["_event_type"] = event_type
            try:
                queue.put_nowait(data)
            except asyncio.QueueFull:
                logger.warning("Event queue full, dropping: %s", event_type)

        try:
            # ── Phase: Init ──
            session = await self._session_manager.create_session(
                profile_snapshot=profile,
                user_id=profile.get("user_id"),
                profile_id=profile.get("id"),
            )
            await self._db.commit()
            yield self._format_sse("session_created", {"session_id": session.id})

            # ── Phase: Planning ──
            yield self._format_sse("activity_log", {
                "message": "正在分析你的画像，规划搜索策略...",
                "level": "info",
            })

            query_plan = self._query_planner.plan(profile)
            await self._session_manager.set_query_plan(
                session, query_plan.model_dump()
            )
            await self._db.commit()
            yield self._format_sse("query_plan_ready", {
                "queries": [q.model_dump() for q in query_plan.queries],
                "active_sources": self._active_source_ids(),
            })

            # PRE_SEARCH hook
            hook_result = await self._hook_engine.run_hooks(
                HookType.PRE_SEARCH,
                {"queries": [q.model_dump() for q in query_plan.queries]},
            )
            if not hook_result.passed:
                yield self._format_sse("search_blocked", {
                    "reason": hook_result.blocked_reason,
                    "warnings": hook_result.warnings,
                })
                await self._session_manager.mark_failed(
                    session,
                    error_message=f"PRE_SEARCH hook blocked: {hook_result.blocked_reason}",
                    search_duration_ms=self._elapsed_ms(start_time),
                )
                await self._db.commit()
                yield self._format_sse("stream_end", {})
                return

            # ── Phase: Searching ──
            yield self._format_sse("phase_start", {
                "phase": "searching",
                "message": f"开始多源搜索（{len(self._adapters)} 个数据源）...",
            })
            source_status: Dict[str, str] = {}
            all_results: List[Dict[str, Any]] = []
            pending_search_tasks: List[asyncio.Task] = []

            for adapter_id, adapter in self._adapters.items():
                perm = self._permission_guard.can_search_source(adapter_id)
                if not perm.allowed:
                    source_status[adapter_id] = f"blocked:{perm.policy.value}"
                    _push("source_error", {"source": adapter_id, "error": f"blocked: {perm.policy.value}"})
                    continue

                yield self._format_sse("activity_log", {
                    "message": f"在{adapter.display_name}搜索「{query_plan.queries[0].query if query_plan.queries else ''}」...",
                    "level": "info",
                })

                task = asyncio.ensure_future(
                    self._search_source_task(session.id, adapter, query_plan, _push)
                )
                pending_search_tasks.append(task)
                active_tasks.append(task)

            # 消费搜索结果直到所有 search task 结束
            while pending_search_tasks:
                done, pending = await asyncio.wait(
                    pending_search_tasks, timeout=0.1
                )
                pending_search_tasks = list(pending)

                for task in done:
                    try:
                        results, adapter_id = task.result()
                        source_status[adapter_id] = "ok"
                        all_results.extend(results)
                    except Exception as e:
                        logger.warning(f"Search task failed: {e}")

                while not queue.empty():
                    event = await queue.get()
                    if event is not None:
                        yield self._format_sse(event.pop("_event_type"), event)

            # 消费剩余队列事件
            while not queue.empty():
                event = await queue.get()
                if event is not None:
                    yield self._format_sse(event.pop("_event_type"), event)

            # ── Phase: Dedup + Rank ──
            yield self._format_sse("phase_start", {
                "phase": "ranking",
                "message": f"搜索完成，正在对 {len(all_results)} 条结果去重排序...",
            })

            deduped_results = self._dedupe_and_filter_results(all_results, query_plan)

            url_counts: Dict[str, int] = {}
            for item in all_results:
                u = item.get("source_url", "")
                url_counts[u] = url_counts.get(u, 0) + 1

            # rank 内置过滤过期内容 + profile 相关度排序
            ranked_results = self._ranker.rank(deduped_results, url_counts, profile=profile)

            # 按时间+置信度筛选 Top N
            top_n = settings.ranking_top_n
            total_before_filter = len(ranked_results)
            ranked_results = ranked_results[:top_n]

            yield self._format_sse("ranking_completed", {
                "final_items": ranked_results,
                "total": len(ranked_results),
                "total_before_filter": total_before_filter,
                "duplicates_removed": len(all_results) - len(deduped_results),
            })

            if total_before_filter > top_n:
                yield self._format_sse("activity_log", {
                    "message": f"从 {total_before_filter} 条结果中按时间和内容质量筛选出 Top {len(ranked_results)} 条",
                    "level": "info",
                })

            # ── search_completed — 搜索阶段结束，前端停止计时 ──
            search_duration_ms = self._elapsed_ms(start_time)

            has_success = any(s == "ok" for s in source_status.values())
            has_failure = any(s != "ok" and not s.startswith("blocked") for s in source_status.values())

            if not has_success:
                await self._session_manager.mark_failed(
                    session,
                    error_message="All sources failed",
                    search_duration_ms=search_duration_ms,
                    source_status=source_status,
                )
                final_status = "failed"
            elif has_failure:
                await self._session_manager.mark_partial_success(
                    session,
                    fresh_count=len(ranked_results),
                    total_count=len(ranked_results),
                    search_duration_ms=search_duration_ms,
                    source_status=source_status,
                )
                final_status = "partial_success"
            else:
                await self._session_manager.mark_success(
                    session,
                    fresh_count=len(ranked_results),
                    total_count=len(ranked_results),
                    search_duration_ms=search_duration_ms,
                    source_status=source_status,
                )
                final_status = "success"

            await self._db.commit()

            yield self._format_sse("search_completed", {
                "session_id": session.id,
                "status": final_status,
                "total": len(ranked_results),
                "search_duration_ms": search_duration_ms,
                "sources_status": source_status,
                "hook_warnings": hook_result.warnings,
            })

            yield self._format_sse("activity_log", {
                "message": f"搜索完成！{search_duration_ms / 1000:.1f} 秒内找到 {len(ranked_results)} 条面经",
                "level": "success",
            })

            # ══════════════════════════════════════════════
            # ── Enhancement Phase（增强阶段，不阻塞搜索） ──
            # ══════════════════════════════════════════════

            fetchable_urls = []
            for item in ranked_results[:settings.webfetch_max_urls]:
                url = item.get("source_url", "")
                source = item.get("source", "")
                perm = self._permission_guard.can_fetch_url(url, source)
                if perm.allowed:
                    fetchable_urls.append(item)

            if fetchable_urls:
                yield self._format_sse("phase_start", {
                    "phase": "fetching",
                    "message": f"开始抓取 {len(fetchable_urls)} 篇文章全文...",
                })
                yield self._format_sse("enhance_start", {
                    "message": "正在深度分析文章内容...",
                    "total_urls": len(fetchable_urls),
                })

                # ── Fetch sub-phase ──
                fetch_tasks = []
                for i, item in enumerate(fetchable_urls):
                    url = item.get("source_url", "")
                    yield self._format_sse("fetch_started", {
                        "index": i + 1,
                        "total": len(fetchable_urls),
                        "source_url": url,
                        "source": item.get("source", ""),
                    })
                    task = asyncio.ensure_future(
                        self._fetch_doc_task(session.id, item, _push)
                    )
                    fetch_tasks.append(task)
                    active_tasks.append(task)

                while fetch_tasks:
                    done, pending = await asyncio.wait(fetch_tasks, timeout=0.1)
                    fetch_tasks = list(pending)
                    while not queue.empty():
                        event = await queue.get()
                        if event is not None:
                            yield self._format_sse(event.pop("_event_type"), event)

                while not queue.empty():
                    event = await queue.get()
                    if event is not None:
                        yield self._format_sse(event.pop("_event_type"), event)

                # Commit fetched docs so extract phase won't hit SQLite lock
                await self._db.commit()

                # ── Extract sub-phase (with timeout + independent DB sessions) ──
                fetched_doc_ids: List[str] = []
                for item in ranked_results[:settings.webfetch_max_urls]:
                    url = item.get("source_url", "")
                    stmt = sa_select(SourceDocumentModel).where(
                        SourceDocumentModel.source_url == url
                    )
                    result = await self._db.execute(stmt)
                    doc = result.scalar_one_or_none()
                    if doc and doc.full_text:
                        fetched_doc_ids.append(doc.id)

                # Release main session's read transaction before extraction
                # (SQLite file-level locking: concurrent writes from extract sessions
                #  will fail if main session holds even a read lock)
                await self._db.commit()

                extracted_count = 0
                if fetched_doc_ids:
                    docs_to_extract = fetched_doc_ids[:5]

                    yield self._format_sse("phase_start", {
                        "phase": "extracting",
                        "message": f"开始 LLM 结构化抽取（{len(docs_to_extract)} 篇）...",
                    })

                    # 并行启动所有 LLM 抽取任务（各自有独立 DB session）
                    extract_tasks = []
                    for i, doc_id in enumerate(docs_to_extract):
                        task = asyncio.ensure_future(
                            self._extract_doc_task_isolated(
                                session.id, doc_id, i, len(docs_to_extract), _push
                            )
                        )
                        extract_tasks.append(task)
                        active_tasks.append(task)

                    # 持续 drain queue 直到所有抽取任务完成
                    while extract_tasks:
                        done, pending = await asyncio.wait(extract_tasks, timeout=0.3)
                        extract_tasks = list(pending)
                        while not queue.empty():
                            event = await queue.get()
                            if event is not None:
                                yield self._format_sse(event.pop("_event_type"), event)

                    # Final drain
                    while not queue.empty():
                        event = await queue.get()
                        if event is not None:
                            yield self._format_sse(event.pop("_event_type"), event)

                    extracted_count = len(docs_to_extract)

                yield self._format_sse("enhance_completed", {
                    "fetched_count": len(fetchable_urls),
                    "extracted_count": extracted_count,
                })
                yield self._format_sse("activity_log", {
                    "message": f"深度分析完成，已解析 {extracted_count} 篇文章",
                    "level": "success",
                })

            yield self._format_sse("stream_end", {})

        except Exception as e:
            logger.exception(f"StreamingCoordinator failed: {e}")
            yield self._format_sse("search_error", {
                "error": str(e),
                "message": "搜索过程发生异常",
            })
            yield self._format_sse("stream_end", {})
        finally:
            for task in active_tasks:
                if not task.done():
                    task.cancel()
            while not queue.empty():
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

    async def _search_source_task(
        self,
        session_id: str,
        adapter: SourceAdapter,
        query_plan,
        push,
    ) -> tuple:
        """搜索单个数据源，结果通过 push 回调实时推送"""
        adapter_id = adapter.id
        started_at = datetime.utcnow()
        timeout = settings.search_timeout_platform
        max_queries_per_source = 4

        push("search_started", {
            "source": adapter_id,
            "display_name": adapter.display_name,
            "queries": [q.query for q in query_plan.queries[:max_queries_per_source]],
        })

        all_results: List[Dict[str, Any]] = []

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
                if isinstance(qr, SourceSearchResult):
                    if qr.status not in {SourceStatus.OK, SourceStatus.EMPTY}:
                        self._source_health.record_status(adapter_id, qr.status, qr.reason)
                        continue
                    search_items = qr.normalized_items()
                else:
                    search_items = []
                    for entry in qr:
                        if isinstance(entry, SourceSearchItem):
                            search_items.append(entry)
                        elif isinstance(entry, SourceSearchResult):
                            search_items.extend(entry.normalized_items())

                for sr in search_items:
                    item = {
                        "source": sr.source,
                        "source_url": sr.source_url,
                        "title": sr.title,
                        "snippet": sr.snippet,
                        "published_at": sr.published_at,
                    }
                    all_results.append(item)

            display_results = self._ranker.rank(
                self._dedupe_and_filter_results(all_results, query_plan),
                profile={},
            )

            push("source_results", {
                "source": adapter_id,
                "items": display_results,
            })

            ended_at = datetime.utcnow()
            duration_ms = int((ended_at - started_at).total_seconds() * 1000)

            push("source_completed", {
                "source": adapter_id,
                "count": len(all_results),
                "duration_ms": duration_ms,
            })

            await self._trace.log_tool_run(
                session_id=session_id,
                tool_name=f"search_{adapter_id}",
                tool_type="search",
                input_data={"query_count": len(queries_to_run), "adapter": adapter_id},
                output_summary={"result_count": len(all_results)},
                status="success",
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
            )

        except asyncio.TimeoutError:
            push("source_timeout", {
                "source": adapter_id,
                "timeout_s": timeout,
            })
            ended_at = datetime.utcnow()
            await self._trace.log_tool_run(
                session_id=session_id,
                tool_name=f"search_{adapter_id}",
                tool_type="search",
                input_data={"adapter": adapter_id},
                status="timeout",
                error_message=f"Timeout after {timeout}s",
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=int((ended_at - started_at).total_seconds() * 1000),
            )

        except Exception as e:
            push("source_error", {
                "source": adapter_id,
                "error": str(e),
            })

        return all_results, adapter_id

    async def _fetch_doc_task(
        self,
        session_id: str,
        item: Dict[str, Any],
        push,
    ) -> None:
        """抓取单篇正文，使用独立 DB session 避免并发锁冲突"""
        url = item.get("source_url", "")
        source = item.get("source", "search_engine")
        started_at = datetime.utcnow()

        try:
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

            if doc and doc.full_text:
                async with async_session_factory() as fetch_db:
                    existing_stmt = sa_select(SourceDocumentModel).where(
                        SourceDocumentModel.source_url == doc.source_url
                    )
                    existing_result = await fetch_db.execute(existing_stmt)
                    existing_doc = existing_result.scalar_one_or_none()

                    if existing_doc:
                        doc_id = existing_doc.id
                    else:
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
                        fetch_db.add(source_doc)
                        doc_id = source_doc.id

                    ended_at = datetime.utcnow()
                    trace = TraceLogger(fetch_db)
                    await trace.log_tool_run(
                        session_id=session_id,
                        tool_name="fetch_web",
                        tool_type="fetch",
                        input_data={"url": url, "source": source},
                        output_summary={"doc_id": doc_id, "text_len": len(doc.full_text)},
                        status="success",
                        started_at=started_at,
                        ended_at=ended_at,
                        duration_ms=int((ended_at - started_at).total_seconds() * 1000),
                    )
                    await fetch_db.commit()

                push("fetch_completed", {
                    "source_url": url,
                    "source": source,
                    "source_document_id": doc_id,
                    "has_full_text": True,
                    "text_length": len(doc.full_text),
                })

            else:
                push("fetch_completed", {
                    "source_url": url,
                    "source": source,
                    "has_full_text": False,
                    "reason": "no_content",
                })

        except asyncio.TimeoutError:
            push("fetch_completed", {
                "source_url": url,
                "source": source,
                "has_full_text": False,
                "reason": "timeout",
            })
            async with async_session_factory() as timeout_db:
                trace = TraceLogger(timeout_db)
                await trace.log_tool_run(
                    session_id=session_id,
                    tool_name="fetch_web",
                    tool_type="fetch",
                    input_data={"url": url},
                    status="timeout",
                    error_message=f"Timeout after {settings.webfetch_timeout}s",
                    started_at=started_at,
                    ended_at=datetime.utcnow(),
                )
                await timeout_db.commit()
        except Exception as e:
            push("fetch_completed", {
                "source_url": url,
                "source": source,
                "has_full_text": False,
                "reason": str(e)[:100],
            })

    async def _extract_doc_task_isolated(
        self,
        session_id: str,
        doc_id: str,
        index: int,
        total: int,
        push,
    ) -> None:
        """
        LLM 流式抽取单篇结构化面试数据。
        使用独立 DB session 避免 SQLite 锁竞争，带 60s 超时。
        通过 llm_chunk 事件实时推送 LLM token 到前端。
        """
        started_at = datetime.utcnow()
        try:
            async with async_session_factory() as extract_db:
                stmt = sa_select(SourceDocumentModel).where(SourceDocumentModel.id == doc_id)
                result = await extract_db.execute(stmt)
                source_doc = result.scalar_one_or_none()
                if not source_doc:
                    push("extract_completed", {
                        "source_document_id": doc_id,
                        "error": "doc not found",
                        "status": "failed",
                        "extraction_status": "failed",
                        "question_count": 0,
                        "representative_questions": [],
                    })
                    return

                if source_doc.source == "official_job":
                    source_doc.extraction_status = "skipped"
                    await extract_db.commit()
                    push("extract_completed", {
                        "source_document_id": doc_id,
                        "status": "skipped",
                        "extraction_status": "skipped",
                        "question_count": 0,
                        "representative_questions": [],
                    })
                    return

                doc_title = source_doc.title or source_doc.source_url[:40]
                push("activity_log", {
                    "message": f"正在分析「{doc_title[:30]}」的面试内容...",
                    "level": "info",
                })
                push("enhance_progress", {
                    "current": index + 1,
                    "total": total,
                    "doc_title": doc_title,
                })

                # Signal frontend to open LLM stream display
                push("llm_start", {
                    "doc_id": doc_id,
                    "doc_title": doc_title[:30],
                })

                # Token-level streaming callback — push every token immediately
                _chunk_buffer = []

                def _on_token(token: str):
                    _chunk_buffer.append(token)
                    push("llm_chunk", {
                        "doc_id": doc_id,
                        "token": token,
                    })

                from app.llm.structured_extract import extract_interview_streaming

                extract_result = await asyncio.wait_for(
                    extract_interview_streaming(
                        db=extract_db,
                        source_doc=source_doc,
                        on_token=_on_token,
                    ),
                    timeout=EXTRACT_TIMEOUT_S,
                )

                await extract_db.commit()

                summary = extract_result.get("summary", "")
                question_count = extract_result.get("question_count", 0)

                push("llm_summary", {
                    "doc_id": doc_id,
                    "doc_title": doc_title[:30],
                    "summary": summary or f"提取了 {question_count} 个面试问题",
                    "question_count": question_count,
                    "status": extract_result.get("status", "unknown"),
                })

                push("extract_completed", {
                    "source_document_id": doc_id,
                    "question_count": question_count,
                    "status": extract_result.get("status", "unknown"),
                    "evidence_coverage": extract_result.get("evidence_coverage", 0.0),
                    "tags": extract_result.get("tags", []),
                    "representative_questions": extract_result.get("representative_questions", []),
                })

                ended_at = datetime.utcnow()
                trace = TraceLogger(extract_db)
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
                await extract_db.commit()

        except asyncio.TimeoutError:
            logger.warning(f"Extraction timed out for doc {doc_id} after {EXTRACT_TIMEOUT_S}s")
            # Flush any tokens that were collected before timeout
            token_count = len(_chunk_buffer)
            push("llm_summary", {
                "doc_id": doc_id,
                "summary": f"分析超时（已收到 {token_count} 个 token），已跳过",
                "status": "timeout",
            })
            push("extract_completed", {
                "source_document_id": doc_id,
                "error": f"timeout ({EXTRACT_TIMEOUT_S}s)",
                "status": "timeout",
                "extraction_status": "timeout",
                "question_count": 0,
                "representative_questions": [],
            })
            push("activity_log", {
                "message": "文章分析超时，已跳过",
                "level": "warning",
            })

        except Exception as e:
            logger.warning(f"Extraction failed for doc {doc_id}: {e}")
            try:
                async with async_session_factory() as failed_db:
                    stmt = sa_select(SourceDocumentModel).where(SourceDocumentModel.id == doc_id)
                    result = await failed_db.execute(stmt)
                    failed_doc = result.scalar_one_or_none()
                    if failed_doc:
                        failed_doc.extraction_status = "failed"
                    await failed_db.commit()
            except Exception as status_exc:
                logger.warning("Failed to mark extraction failed for doc %s: %s", doc_id, status_exc)
            push("llm_summary", {
                "doc_id": doc_id,
                "summary": f"分析失败: {str(e)[:50]}",
                "status": "error",
            })
            push("extract_completed", {
                "source_document_id": doc_id,
                "error": str(e)[:100],
                "status": "failed",
                "extraction_status": "failed",
                "question_count": 0,
                "representative_questions": [],
            })

    def _dedupe_and_filter_results(self, items: list[dict[str, Any]], query_plan) -> list[dict[str, Any]]:
        seen_urls: set[str] = set()
        filtered: list[dict[str, Any]] = []
        target_companies = [q.company for q in query_plan.queries if q.company]
        target_positions = [q.position for q in query_plan.queries if q.position]

        for item in items:
            url = item.get("source_url", "")
            if not url or url in seen_urls:
                continue
            seen_urls.add(url)
            if not self._is_display_candidate(item, target_companies, target_positions):
                continue
            filtered.append(item)
        return filtered

    @staticmethod
    def _is_display_candidate(
        item: dict[str, Any],
        target_companies: list[str],
        target_positions: list[str],
    ) -> bool:
        if item.get("source") == "official_job":
            return True

        text = f"{item.get('title', '')} {item.get('snippet', '')}".lower()
        compact_text = re.sub(r"\s+", "", text)
        if item.get("source") == "search_engine" and not StreamingCoordinator._looks_like_interview(text):
            return False

        if target_companies and not any(company.lower() in text for company in target_companies):
            return False

        if target_positions:
            position_terms = StreamingCoordinator._position_terms(target_positions)
            if position_terms and not any(term in text or term in compact_text for term in position_terms):
                return False

        return True

    @staticmethod
    def _looks_like_interview(text: str) -> bool:
        return bool(re.search(r"(面经|面试|一面|二面|三面|笔试|追问|手撕|八股|项目)", text, re.IGNORECASE))

    @staticmethod
    def _position_terms(positions: list[str]) -> list[str]:
        terms: list[str] = []
        for position in positions:
            compact = re.sub(r"\s+", "", position.lower())
            if not compact:
                continue
            terms.append(compact)
            for suffix in ("开发", "工程师", "方向", "岗位"):
                compact = compact.replace(suffix, "")
            if len(compact) >= 2:
                terms.append(compact)
        return list(dict.fromkeys(terms))

    def _active_source_ids(self) -> List[str]:
        """返回当前启用的 source adapter 列表"""
        active = []
        for adapter_id in self._adapters:
            perm = self._permission_guard.can_search_source(adapter_id)
            if perm.allowed:
                active.append(adapter_id)
        return active

    def _format_sse(self, event_type: str, data: dict) -> str:
        """格式化为 SSE 文本"""
        payload = json.dumps(data, ensure_ascii=False, default=str)
        return f"id: {_sse_id()}\nevent: {event_type}\ndata: {payload}\n\n"

    def _elapsed_ms(self, start_time: float) -> int:
        return int((time.time() - start_time) * 1000)
