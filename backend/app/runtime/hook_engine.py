import logging
from enum import Enum
from typing import Any, Callable, Awaitable, Dict, List, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class HookType(str, Enum):
    PRE_SEARCH = "pre_search"
    POST_SEARCH = "post_search"
    PRE_FETCH = "pre_fetch"
    POST_FETCH = "post_fetch"
    POST_EXTRACT = "post_extract"
    POST_RANK = "post_rank"


class HookResult(BaseModel):
    passed: bool
    warnings: List[str] = []
    blocked_reason: Optional[str] = None


HookFn = Callable[[Dict[str, Any]], Awaitable[HookResult]]


class HookEngine:
    """
    质量门禁引擎。
    在搜索、抓取、抽取、排序前后执行注册的 Hook 函数。
    Hook 不是业务逻辑，而是验证和过滤。
    """

    def __init__(self):
        self._hooks: Dict[HookType, List[HookFn]] = {ht: [] for ht in HookType}

    def register(self, hook_type: HookType, fn: HookFn) -> None:
        self._hooks[hook_type].append(fn)

    async def run_hooks(self, hook_type: HookType, context: Dict[str, Any]) -> HookResult:
        """
        依次执行指定类型的所有 Hook。
        任何一个 Hook 返回 passed=False 则整体 blocked。
        所有 warnings 会汇总。
        """
        all_warnings: List[str] = []

        for fn in self._hooks[hook_type]:
            try:
                result = await fn(context)
                all_warnings.extend(result.warnings)
                if not result.passed:
                    return HookResult(
                        passed=False,
                        warnings=all_warnings,
                        blocked_reason=result.blocked_reason,
                    )
            except Exception as e:
                logger.warning(f"Hook {fn.__name__} raised exception: {e}")
                all_warnings.append(f"Hook {fn.__name__} error: {str(e)}")

        return HookResult(passed=True, warnings=all_warnings)


# --- 默认 Hook 实现 ---

_INTERVIEW_KEYWORDS = (
    "一面", "二面", "三面", "HR面", "面试官", "追问", "手撕",
    "算法题", "项目", "八股", "反问", "offer", "挂了", "oc",
    "实习", "校招", "社招", "笔试", "面经",
)


async def pre_search_hook(context: Dict[str, Any]) -> HookResult:
    """检查搜索查询质量"""
    queries = context.get("queries", [])
    warnings = []

    if not queries:
        return HookResult(passed=False, blocked_reason="No queries provided")

    if len(queries) > 20:
        warnings.append(f"Query count {len(queries)} exceeds limit 20, will truncate")

    for q in queries:
        query_text = q if isinstance(q, str) else q.get("query", "")
        if len(query_text) < 4:
            warnings.append(f"Query too short: '{query_text}'")

    return HookResult(passed=True, warnings=warnings)


async def post_search_hook(context: Dict[str, Any]) -> HookResult:
    """检查搜索结果质量"""
    results = context.get("results", [])
    warnings = []

    if not results:
        warnings.append("Search returned 0 results")
        return HookResult(passed=True, warnings=warnings)

    urls = [r.get("source_url", "") for r in results if isinstance(r, dict)]
    unique_urls = set(urls)
    if len(urls) > 0 and len(unique_urls) < len(urls) * 0.5:
        warnings.append("High duplicate URL ratio in search results")

    return HookResult(passed=True, warnings=warnings)


async def post_fetch_hook(context: Dict[str, Any]) -> HookResult:
    """检查抓取内容质量"""
    full_text = context.get("full_text", "")
    warnings = []

    if not full_text or len(full_text) < 50:
        warnings.append("Fetched content too short, likely not a real article")
        return HookResult(passed=True, warnings=warnings)

    has_interview_signal = any(kw in full_text for kw in _INTERVIEW_KEYWORDS)
    if not has_interview_signal:
        warnings.append("Content lacks interview-related keywords")

    return HookResult(passed=True, warnings=warnings)


def create_default_hook_engine() -> HookEngine:
    """创建带有默认 Hook 的 HookEngine"""
    engine = HookEngine()
    engine.register(HookType.PRE_SEARCH, pre_search_hook)
    engine.register(HookType.POST_SEARCH, post_search_hook)
    engine.register(HookType.POST_FETCH, post_fetch_hook)
    return engine
