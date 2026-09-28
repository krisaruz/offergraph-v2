from abc import ABC, abstractmethod
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel


class SourceStatus(str, Enum):
    OK = "ok"
    EMPTY = "empty"
    ERROR = "error"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    DISABLED = "disabled"
    CONFIG_ERROR = "config_error"
    AUTH_REQUIRED = "auth_required"
    UNAUTHORIZED = "unauthorized"


class SourceQuery(BaseModel):
    """Normalized search query passed to source adapters."""

    query: str
    company: Optional[str] = None
    position: Optional[str] = None
    candidate_type: Optional[str] = None
    region: Optional[str] = None
    limit: int = 10


class SourceSearchItem(BaseModel):
    """Single normalized search hit from a source."""

    source: str
    source_url: str
    title: str
    snippet: Optional[str] = None
    published_at: Optional[str] = None
    raw: dict = {}


class SourceSearchResult(BaseModel):
    """Source search outcome.

    Legacy adapters still return list[SourceSearchResult] as individual hits.
    Newer runtime code uses this envelope with status/items. Keeping both
    shapes here lets the migration converge around one source contract.
    """

    source: str
    status: SourceStatus = SourceStatus.OK
    items: List[SourceSearchItem] = []
    count: int = 0
    reason: Optional[str] = None

    source_url: Optional[str] = None
    title: Optional[str] = None
    snippet: Optional[str] = None
    published_at: Optional[str] = None
    raw: dict = {}

    def normalized_items(self) -> List[SourceSearchItem]:
        if self.items:
            return self.items
        if self.source_url and self.title:
            return [
                SourceSearchItem(
                    source=self.source,
                    source_url=self.source_url,
                    title=self.title,
                    snippet=self.snippet,
                    published_at=self.published_at,
                    raw=self.raw,
                )
            ]
        return []


class SourceDocument(BaseModel):
    """Fetched source document."""

    source: str
    source_url: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    full_text: Optional[str] = None
    published_at: Optional[str] = None
    content_hash: Optional[str] = None
    raw: dict = {}


class SourceAdapter(ABC):
    """Base interface implemented by each source adapter."""

    id: str
    display_name: str

    @property
    @abstractmethod
    def capabilities(self) -> dict:
        """Declare supported adapter capabilities."""
        pass

    @abstractmethod
    async def search(self, query: SourceQuery) -> List[SourceSearchResult] | SourceSearchResult:
        pass

    async def fetch(self, url: str) -> Optional[SourceDocument]:
        """Optionally fetch full text for a source URL."""
        return None
