"""公司面试画像服务 — 只统计高可信真实问题"""

import json
import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.interview_event import InterviewEvent
from app.models.question import InterviewQuestion
from app.models.evidence import QuestionEvidence
from app.models.source_document import SourceDocumentModel

logger = logging.getLogger(__name__)

# 高可信阈值
MIN_EVIDENCE_COVERAGE = 0.5
MIN_EXTRACTION_CONFIDENCE = 0.7
MIN_REAL_QUESTIONS_FOR_PROFILE = 20
MIN_HIGH_CONFIDENCE_EVENTS = 2


class CompanyProfileService:
    """
    生成公司面试画像。
    只基于高可信真实面经数据统计，排除低质量样本。
    """

    def __init__(self, db: AsyncSession):
        self._db = db

    async def get_company_profile(
        self,
        company: str,
        position: Optional[str] = None,
        candidate_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """获取公司面试画像"""
        # 查询高可信 interview_events
        conditions = [
            InterviewEvent.company == company,
            InterviewEvent.evidence_coverage >= MIN_EVIDENCE_COVERAGE,
        ]
        if position:
            conditions.append(InterviewEvent.position == position)
        if candidate_type:
            conditions.append(InterviewEvent.candidate_type == candidate_type)

        stmt = select(InterviewEvent).where(and_(*conditions))
        result = await self._db.execute(stmt)
        events = result.scalars().all()

        if len(events) < MIN_HIGH_CONFIDENCE_EVENTS:
            return {
                "company": company,
                "position": position,
                "sufficient_data": False,
                "event_count": len(events),
                "message": f"需要至少 {MIN_HIGH_CONFIDENCE_EVENTS} 条高可信面经才能生成画像",
            }

        # 获取高可信真实问题
        event_ids = [e.id for e in events]
        q_stmt = select(InterviewQuestion).where(
            and_(
                InterviewQuestion.interview_event_id.in_(event_ids),
                InterviewQuestion.source_type == "real_interview",
                InterviewQuestion.confidence >= MIN_EXTRACTION_CONFIDENCE,
            )
        )
        q_result = await self._db.execute(q_stmt)
        questions = q_result.scalars().all()

        # 统计高频问题
        question_freq: Dict[str, Dict[str, Any]] = {}
        for q in questions:
            normalized = q.normalized_question or q.question_text
            key = normalized.strip()[:100]
            if key not in question_freq:
                question_freq[key] = {
                    "text": q.question_text,
                    "category": q.category,
                    "count": 0,
                    "difficulties": [],
                    "tags": set(),
                }
            question_freq[key]["count"] += 1
            if q.difficulty:
                question_freq[key]["difficulties"].append(q.difficulty)
            if q.tags_json:
                try:
                    tags = json.loads(q.tags_json)
                    question_freq[key]["tags"].update(tags)
                except json.JSONDecodeError:
                    pass

        # 排序并格式化
        sorted_questions = sorted(question_freq.values(), key=lambda x: x["count"], reverse=True)
        high_freq_questions = []
        for q in sorted_questions[:30]:
            avg_difficulty = (
                round(sum(q["difficulties"]) / len(q["difficulties"]), 1)
                if q["difficulties"] else None
            )
            high_freq_questions.append({
                "text": q["text"],
                "category": q["category"],
                "frequency": q["count"],
                "avgDifficulty": avg_difficulty,
                "tags": list(q["tags"])[:5],
                "sourceType": "real_interview",
            })

        # 统计分类分布
        category_dist: Dict[str, int] = {}
        for q in questions:
            cat = q.category or "other"
            category_dist[cat] = category_dist.get(cat, 0) + 1

        # 难度统计
        difficulties = [e.difficulty for e in events if e.difficulty]
        avg_difficulty = round(sum(difficulties) / len(difficulties), 1) if difficulties else None

        return {
            "company": company,
            "position": position,
            "candidateType": candidate_type,
            "sufficient_data": True,
            "eventCount": len(events),
            "questionCount": len(questions),
            "avgDifficulty": avg_difficulty,
            "categoryDistribution": category_dist,
            "highFreqQuestions": high_freq_questions,
            "generatedAt": None,
        }
