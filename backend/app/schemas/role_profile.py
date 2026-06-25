from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class RoleProfileSearchRequest(BaseModel):
    keyword: str = Field(..., min_length=2, max_length=200)
    identity: str = "working_switch"
    regions: Optional[List[str]] = None


class ParsedRoleQuery(BaseModel):
    keyword: str
    companies: List[str]
    directions: List[str]
    normalizedTerms: List[str] = []


class RoleProfileEvidence(BaseModel):
    evidenceType: str
    source: str
    sourceUrl: str
    title: Optional[str] = None
    quote: Optional[str] = None
    confidence: float = 0.0
    publishedAt: Optional[str] = None
    limitations: List[str] = []


class SkillWeight(BaseModel):
    skill: str
    weight: float
    evidenceCount: int = 0
    reason: str


class PreparationAction(BaseModel):
    priority: str
    action: str
    reason: str


class RoleProfileResult(BaseModel):
    targetRole: str
    companies: List[str]
    direction: str
    confidence: str
    roleSummary: str
    businessScenarios: List[str]
    skillWeights: List[SkillWeight]
    interviewFocus: List[str]
    preparationPlan: List[PreparationAction]
    evidence: List[RoleProfileEvidence]
    evidenceStats: Dict[str, Any]
    limitations: List[str] = []


class RoleProfileSearchResponse(BaseModel):
    sessionId: str
    status: str
    parsedQuery: ParsedRoleQuery
    profile: RoleProfileResult
    sourcesStatus: Dict[str, Any]
    searchDuration: int = 0
    qualityReport: Dict[str, Any] = {}
