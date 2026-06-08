"""
Source Adapter 注册表。
启动时根据配置注册可用的 adapter。
"""

import logging
from typing import Dict

from app.adapters.base import SourceAdapter
from app.config import settings

logger = logging.getLogger(__name__)

_registry: Dict[str, SourceAdapter] = {}
_initialized = False


def register_adapter(adapter: SourceAdapter) -> None:
    _registry[adapter.id] = adapter


def _ensure_initialized() -> None:
    global _initialized
    if _initialized:
        return
    _initialized = True

    if settings.nowcoder_enabled:
        from app.adapters.nowcoder import NowcoderAdapter
        register_adapter(NowcoderAdapter())
        logger.info("Registered adapter: nowcoder")

    if settings.maimai_enabled:
        from app.adapters.maimai import MaimaiAdapter
        register_adapter(MaimaiAdapter(cookie=settings.maimai_cookie))
        logger.info("Registered adapter: maimai (cookie=%s)", "configured" if settings.maimai_cookie else "none")

    if settings.xhs_enabled:
        from app.adapters.xiaohongshu import XiaohongshuAdapter
        xhs_adapter = XiaohongshuAdapter(mcp_command=settings.xhs_mcp_command)
        xhs_adapter.start_warmup()
        register_adapter(xhs_adapter)
        logger.info("Registered adapter: xiaohongshu (via MCP, warmup started)")

    if settings.search_api_key:
        from app.adapters.search_engine import SearchEngineAdapter
        register_adapter(SearchEngineAdapter())
        logger.info("Registered adapter: search_engine")


def get_registered_adapters() -> Dict[str, SourceAdapter]:
    _ensure_initialized()
    return dict(_registry)
