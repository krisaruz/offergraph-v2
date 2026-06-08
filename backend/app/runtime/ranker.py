"""排序引擎 — 时间优先 + 内容质量评估"""

import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.config import settings

logger = logging.getLogger(__name__)


class TrustScore(BaseModel):
    """可信度评分各维度"""
    relevance: float = 0.5
    source_reliability: float = 0.5
    evidence_coverage: float = 0.0
    freshness: float = 0.3
    content_richness: float = 0.0
    duplicate_support: float = 0.0
    extraction_confidence: float = 0.0


SOURCE_RELIABILITY = {
    "nowcoder": 0.9,
    "maimai": 0.7,
    "xiaohongshu": 0.6,
    "search_engine": 0.6,
    "zhihu.com": 0.7,
    "juejin.cn": 0.65,
}

# 相关度是最重要的排序因子，然后是时间和内容质量
WEIGHTS = {
    "relevance": 0.30,
    "freshness": 0.25,
    "content_richness": 0.20,
    "source_reliability": 0.10,
    "evidence_coverage": 0.08,
    "duplicate_support": 0.04,
    "extraction_confidence": 0.03,
}

# 身份到候选类型的映射（与 query_planner 保持一致）
_IDENTITY_MAP = {
    "student_autumn": "校招",
    "student_spring": "校招",
    "student_summer_intern": "实习",
    "student_daily_intern": "实习",
    "working_switch": "社招",
    "working_pivot": "社招",
}

# 标题/片段中暗示高质量面经内容的关键词
_RICHNESS_KEYWORDS = [
    "面经", "面试题", "一面", "二面", "三面", "hr面",
    "offer", "oc", "已offer", "已上岸",
    "算法题", "手撕", "项目", "八股", "场景题",
    "全流程", "详细", "复盘", "总结",
]

# 从标题/snippet中提取日期的模式
_DATE_PATTERNS = [
    re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日?"),
    re.compile(r"(\d{4})[.\-/](\d{1,2})[.\-/](\d{1,2})"),
    re.compile(r"(\d{4})\.(\d{1,2})"),
]

# 时间文本关键词
_RECENCY_HINTS = {
    "今天": 0, "昨天": 1, "前天": 2,
    "1天前": 1, "2天前": 2, "3天前": 3,
    "1周前": 7, "一周前": 7,
    "2周前": 14, "两周前": 14,
    "1个月前": 30, "一个月前": 30,
    "2个月前": 60, "两个月前": 60,
    "3个月前": 90, "三个月前": 90,
}


class Ranker:
    """
    排序器：时间最新 + 内容最丰富的面经排在最前。

    排序逻辑：
    1. 时间 (35%) — 近期内容优先，从标题/snippet/published_at中推断
    2. 内容丰富度 (30%) — 标题中包含面试轮次、题目数量等关键词
    3. 来源可信度 (15%) — 牛客 > 脉脉 > 小红书
    4. 证据覆盖 (10%) — LLM 抽取后的结构化覆盖率
    5. 其他 (10%)
    """

    def rank(
        self,
        items: List[Dict[str, Any]],
        url_counts: Dict[str, int] | None = None,
        filter_expired: bool = True,
        profile: Dict[str, Any] | None = None,
    ) -> List[Dict[str, Any]]:
        """
        排序 + 可选过滤，单次遍历完成，避免重复计算。
        profile 用于计算相关度（公司/方向/身份匹配度）。
        """
        if not items:
            return []

        url_counts = url_counts or {}
        max_age_days = settings.max_content_age_days if filter_expired else 0
        scored_items = []
        filtered_count = 0

        # 提取 profile 关键词用于相关度计算
        relevance_keywords = self._extract_relevance_keywords(profile)

        for item in items:
            age_days = self._extract_age_days(item)

            if max_age_days > 0 and age_days is not None and age_days > max_age_days:
                filtered_count += 1
                continue

            if age_days is None:
                item["_unknown_age"] = True

            trust = self._compute_trust_score(
                item, url_counts, age_days=age_days,
                relevance_keywords=relevance_keywords,
            )
            final_score = self._compute_final_score(trust)

            item["trust_score"] = trust.model_dump()
            item["final_score"] = final_score
            item["trust_label"] = self._trust_label(trust)
            scored_items.append(item)

        if filtered_count > 0:
            logger.info(
                f"Age filter: {len(items)} → {len(scored_items)} "
                f"(removed {filtered_count} expired)"
            )

        scored_items.sort(key=lambda x: x["final_score"], reverse=True)
        return scored_items

    def _extract_age_days(self, item: Dict[str, Any]) -> Optional[int]:
        """提取内容年龄（天数），无法判断返回 None"""
        published_at = item.get("published_at")
        text_context = f"{item.get('title', '')} {item.get('snippet', '')}".lower()

        # 优先使用 published_at
        if published_at:
            try:
                if isinstance(published_at, str):
                    pub_date = datetime.fromisoformat(
                        published_at.replace("Z", "+00:00")
                    )
                else:
                    pub_date = published_at
                now = datetime.utcnow()
                if pub_date.tzinfo:
                    now = now.replace(tzinfo=pub_date.tzinfo)
                return max((now - pub_date).days, 0)
            except (ValueError, TypeError):
                pass

        # 从文本中提取日期
        for pattern in _DATE_PATTERNS:
            match = pattern.search(text_context)
            if match:
                groups = match.groups()
                try:
                    year = int(groups[0])
                    month = int(groups[1])
                    day = int(groups[2]) if len(groups) > 2 else 15
                    dt = datetime(year, month, day)
                    return max((datetime.utcnow() - dt).days, 0)
                except (ValueError, IndexError):
                    pass

        # 相对时间提示
        for hint, days in _RECENCY_HINTS.items():
            if hint in text_context:
                return days

        # 标题中含年份
        year_match = re.search(r"20(1[89]|2[0-6])", text_context)
        if year_match:
            year = int("20" + year_match.group(1))
            return (datetime.utcnow().year - year) * 365

        return None

    def _compute_trust_score(
        self,
        item: Dict[str, Any],
        url_counts: Dict[str, int],
        age_days: Optional[int] = None,
        relevance_keywords: Dict[str, List[str]] | None = None,
    ) -> TrustScore:
        source = item.get("source", "")
        source_url = item.get("source_url", "")
        title = item.get("title", "")
        snippet = item.get("snippet", "")
        text_context = f"{title} {snippet}".lower()

        # 相关度：匹配 profile 中的公司、方向、身份
        relevance = self._compute_relevance(text_context, relevance_keywords)

        # 来源可信度
        source_reliability = SOURCE_RELIABILITY.get(source, 0.5)
        for domain, reliability in SOURCE_RELIABILITY.items():
            if domain in source_url:
                source_reliability = max(source_reliability, reliability)
                break

        # 时效性：复用已提取的 age_days，避免重复计算
        if age_days is not None:
            freshness = self._age_to_freshness(timedelta(days=age_days))
        else:
            freshness = self._compute_freshness(
                published_at=item.get("published_at"),
                text_context=text_context,
            )

        # 内容丰富度：基于标题/snippet的关键词密度
        content_richness = self._compute_content_richness(title, snippet)

        # 证据覆盖（LLM 抽取后才有值）
        evidence_coverage = item.get("evidence_coverage", 0.0)
        extraction_confidence = item.get("extraction_confidence", 0.0)

        # 多篇支持
        url = item.get("source_url", "")
        count = url_counts.get(url, 1)
        duplicate_support = min(count / 3.0, 1.0)

        return TrustScore(
            relevance=relevance,
            source_reliability=source_reliability,
            freshness=freshness,
            content_richness=content_richness,
            evidence_coverage=evidence_coverage,
            duplicate_support=duplicate_support,
            extraction_confidence=extraction_confidence,
        )

    def _compute_final_score(self, trust: TrustScore) -> float:
        return (
            trust.relevance * WEIGHTS["relevance"]
            + trust.freshness * WEIGHTS["freshness"]
            + trust.content_richness * WEIGHTS["content_richness"]
            + trust.source_reliability * WEIGHTS["source_reliability"]
            + trust.evidence_coverage * WEIGHTS["evidence_coverage"]
            + trust.duplicate_support * WEIGHTS["duplicate_support"]
            + trust.extraction_confidence * WEIGHTS["extraction_confidence"]
        )

    @staticmethod
    def _extract_relevance_keywords(profile: Dict[str, Any] | None) -> Dict[str, List[str]]:
        """从 profile 中提取用于相关度匹配的关键词"""
        if not profile:
            return {"companies": [], "directions": [], "identity_labels": []}

        companies = profile.get("target_companies", [])
        if isinstance(companies, str):
            import json as _json
            try:
                companies = _json.loads(companies)
            except (ValueError, TypeError):
                companies = []

        directions = profile.get("directions", [])
        if isinstance(directions, str):
            import json as _json
            try:
                directions = _json.loads(directions)
            except (ValueError, TypeError):
                directions = []

        identity = profile.get("identity", "")
        identity_labels = []
        label = _IDENTITY_MAP.get(identity, "")
        if label:
            identity_labels.append(label)
        # 负标签：不属于的身份类型
        all_labels = set(_IDENTITY_MAP.values())
        negative_labels = list(all_labels - set(identity_labels))

        return {
            "companies": [c.lower() for c in companies],
            "directions": [d.lower() for d in directions],
            "identity_labels": [l.lower() for l in identity_labels],
            "negative_labels": [l.lower() for l in negative_labels],
        }

    @staticmethod
    def _compute_relevance(
        text_context: str, keywords: Dict[str, List[str]] | None
    ) -> float:
        """
        根据 profile 匹配度计算相关度：
        - 命中目标公司: +0.3
        - 命中目标方向: +0.3
        - 命中身份类型(社招/校招/实习): +0.3
        - 命中错误身份类型: -0.4 (大幅降权)
        - 基础分: 0.1 (无 profile 时所有内容平等)
        """
        if not keywords:
            return 0.5

        score = 0.1

        # 公司匹配
        for company in keywords.get("companies", []):
            if company in text_context:
                score += 0.3
                break

        # 方向匹配
        for direction in keywords.get("directions", []):
            if direction in text_context:
                score += 0.3
                break

        # 正确身份匹配
        for label in keywords.get("identity_labels", []):
            if label in text_context:
                score += 0.3
                break

        # 错误身份惩罚（搜社招却出现实习/校招）
        for neg in keywords.get("negative_labels", []):
            if neg in text_context:
                score -= 0.4
                break

        return max(min(score, 1.0), 0.0)

    def _compute_freshness(
        self, published_at: Optional[str], text_context: str = ""
    ) -> float:
        """
        多来源推断时效性：
        1. published_at 字段（最准确）
        2. 标题/snippet 中的日期文本
        3. 相对时间提示（"3天前"、"昨天"）
        """
        # 优先使用 published_at
        if published_at:
            score = self._date_to_freshness(published_at)
            if score is not None:
                return score

        # 从文本中提取日期
        for pattern in _DATE_PATTERNS:
            match = pattern.search(text_context)
            if match:
                groups = match.groups()
                try:
                    year = int(groups[0])
                    month = int(groups[1])
                    day = int(groups[2]) if len(groups) > 2 else 15
                    dt = datetime(year, month, day)
                    return self._age_to_freshness(datetime.utcnow() - dt)
                except (ValueError, IndexError):
                    pass

        # 相对时间提示
        for hint, days in _RECENCY_HINTS.items():
            if hint in text_context:
                return self._age_to_freshness(timedelta(days=days))

        # 标题中含年份（2018-2026）
        year_match = re.search(r"20(1[89]|2[0-6])", text_context)
        if year_match:
            year = int("20" + year_match.group(1))
            age_years = datetime.utcnow().year - year
            if age_years == 0:
                return 1.0
            elif age_years == 1:
                return 0.5
            elif age_years == 2:
                return 0.2
            else:
                return 0.05

        return 0.5

    @staticmethod
    def _date_to_freshness(published_at: str) -> Optional[float]:
        try:
            if isinstance(published_at, str):
                pub_date = datetime.fromisoformat(
                    published_at.replace("Z", "+00:00")
                )
            else:
                pub_date = published_at
        except (ValueError, TypeError):
            return None

        now = datetime.utcnow()
        if pub_date.tzinfo:
            now = now.replace(tzinfo=pub_date.tzinfo)

        return Ranker._age_to_freshness(now - pub_date)

    @staticmethod
    def _age_to_freshness(age: timedelta) -> float:
        """时间越近分数越高，6 个月内权重一致，之后急剧衰减"""
        days = max(age.days, 0)
        if days <= 180:  # 6 个月内：权重一致
            return 1.0
        elif days <= 365:  # 6 个月 - 1 年
            return 0.5
        elif days <= 730:  # 1-2 年
            return 0.2
        else:  # 超过 2 年
            return 0.05

    @staticmethod
    def _compute_content_richness(title: str, snippet: str) -> float:
        """
        基于标题和摘要评估内容的丰富度/面经价值。
        包含更多面试轮次、题目关键词的内容得分更高。
        """
        text = f"{title} {snippet}".lower()
        hit_count = sum(1 for kw in _RICHNESS_KEYWORDS if kw in text)

        # 标题长度也是信息量的指标
        title_length_bonus = min(len(title) / 40.0, 0.3)

        # snippet 长度
        snippet_length_bonus = min(len(snippet or "") / 100.0, 0.2)

        # 关键词命中得分（最多 0.5）
        keyword_score = min(hit_count / 4.0, 0.5)

        return min(keyword_score + title_length_bonus + snippet_length_bonus, 1.0)

    @staticmethod
    def _trust_label(trust: TrustScore) -> str:
        """生成可信度标签"""
        labels = []
        if trust.freshness >= 0.7:
            labels.append("近期内容")
        if trust.content_richness >= 0.6:
            labels.append("内容详细")
        if trust.source_reliability >= 0.8:
            labels.append("真实来源")
        if trust.evidence_coverage >= 0.8:
            labels.append("证据充分")
        elif trust.evidence_coverage >= 0.5:
            labels.append("部分证据")
        if trust.duplicate_support >= 0.5:
            labels.append("多篇支持")
        return " / ".join(labels) if labels else "待验证"
