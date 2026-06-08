from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class FeedSearchRequest(BaseModel):
    """Feed 搜索请求，直接传入画像信息"""
    identity: str = "working_switch"
    directions: List[str] = []
    target_companies: List[str] = []
    regions: Optional[List[str]] = None
    custom_needs: Optional[str] = None


class FeedItem(BaseModel):
    source: str
    source_url: str
    title: Optional[str] = None
    snippet: Optional[str] = None
    published_at: Optional[str] = None
    trust_label: Optional[str] = None
    has_full_text: bool = False
    final_score: Optional[float] = None


class QualityReport(BaseModel):
    filteredCount: int = 0
    duplicateCount: int = 0
    hookWarnings: List[str] = []
    evidenceCoverageAvg: Optional[float] = None
    fetchedCount: int = 0


class FeedSearchResponse(BaseModel):
    sessionId: str
    status: str
    items: List[FeedItem]
    total: int
    sourcesStatus: Dict[str, str]
    cachedCount: int = 0
    freshCount: int = 0
    searchDuration: int = 0
    qualityReport: Optional[QualityReport] = None
    error: Optional[str] = None


class SearchSessionResponse(BaseModel):
    id: str
    status: str
    profileSnapshot: Optional[Dict[str, Any]] = None
    queryPlan: Optional[Any] = None
    sourceStatus: Optional[Dict[str, str]] = None
    toolRuns: List[Dict[str, Any]] = []
    qualityReport: Optional[Dict[str, Any]] = None
    createdAt: Optional[str] = None
