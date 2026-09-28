from typing import Any, Literal

from pydantic import BaseModel, Field


ReportStatus = Literal[
    "ready",
    "sample_insufficient",
    "blocked_source_unready",
    "failed_runtime",
    "cancelled",
]

SourceHealthStatus = Literal[
    "ready",
    "not_connected",
    "expired",
    "captcha_required",
    "rate_limited",
    "timeout",
    "parse_error",
    "disabled",
]


class TargetBrief(BaseModel):
    company: str = Field(min_length=1)
    roleDirection: str = Field(min_length=1)
    experienceStage: Literal["intern", "campus", "social"]
    region: str | None = None
    timeWindowDays: int = Field(default=180, ge=1, le=1095)
    focusTopics: list[str] = []


class SourceHealth(BaseModel):
    source: Literal["xiaohongshu", "maimai", "nowcoder"]
    status: SourceHealthStatus
    lastValidatedAt: str | None = None
    reason: str | None = None
    nextAction: Literal["connect", "relogin", "retry", "wait", "inspect"] | None = None


class SampleQuality(BaseModel):
    validInterviewCount: int = 0
    participatingKeySourceCount: int = 0
    evidenceQuestionCount: int = 0
    meetsFormalReportThreshold: bool = False
    reason: str | None = None


class EvidenceSource(BaseModel):
    id: str
    source: str
    sourceUrl: str
    title: str
    publishedAt: str | None = None
    snippet: str | None = None


class InterviewQuestionEvidence(BaseModel):
    question: str
    evidenceQuote: str
    sourceUrl: str
    source: str


class QuestionCluster(BaseModel):
    id: str
    title: str
    category: str = "other"
    sourceCount: int
    evidenceCount: int
    isTrendQualified: bool
    questions: list[InterviewQuestionEvidence]


class PreparationAdvice(BaseModel):
    clusterId: str
    title: str
    rationale: str


class SourceDiagnostic(BaseModel):
    blockedSources: list[SourceHealth]
    successfulSources: list[SourceHealth]
    message: str


class IntelligenceReport(BaseModel):
    summary: dict[str, Any]
    clusters: list[QuestionCluster]
    evidenceSources: list[EvidenceSource]
    preparationAdvice: list[PreparationAdvice]


class ReportRun(BaseModel):
    id: str
    targetBrief: TargetBrief
    status: ReportStatus
    reportVersion: str = "v3.0"
    sourceHealthSnapshot: list[SourceHealth]
    sampleQuality: SampleQuality
    intelligenceReport: IntelligenceReport | None = None
    diagnostic: SourceDiagnostic | None = None
    createdAt: str
    completedAt: str | None = None


class ReportRunResponse(BaseModel):
    reportRun: ReportRun
