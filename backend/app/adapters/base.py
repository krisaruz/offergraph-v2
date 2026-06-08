from abc import ABC, abstractmethod
from typing import List, Optional

from pydantic import BaseModel


class SourceQuery(BaseModel):
    """统一搜索查询参数"""
    query: str
    company: Optional[str] = None
    position: Optional[str] = None
    candidate_type: Optional[str] = None
    region: Optional[str] = None
    limit: int = 10


class SourceSearchResult(BaseModel):
    """单条搜索结果"""
    source: str
    source_url: str
    title: str
    snippet: Optional[str] = None
    published_at: Optional[str] = None
    raw: dict = {}


class SourceDocument(BaseModel):
    """抓取后的文档"""
    source: str
    source_url: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    full_text: Optional[str] = None
    published_at: Optional[str] = None
    content_hash: Optional[str] = None
    raw: dict = {}


class SourceAdapter(ABC):
    """
    Source Adapter 基类。
    每个平台（牛客、脉脉、小红书、搜索引擎）实现此接口。
    """
    id: str
    display_name: str

    @property
    @abstractmethod
    def capabilities(self) -> dict:
        """声明该来源支持哪些能力"""
        pass

    @abstractmethod
    async def search(self, query: SourceQuery) -> List[SourceSearchResult]:
        pass

    async def fetch(self, url: str) -> Optional[SourceDocument]:
        """可选：抓取 URL 正文。不支持的来源返回 None"""
        return None
