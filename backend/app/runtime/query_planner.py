import logging
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class PlannedQuery(BaseModel):
    """一条计划中的搜索查询"""
    query: str
    company: Optional[str] = None
    position: Optional[str] = None
    candidate_type: Optional[str] = None
    region: Optional[str] = None
    priority: int = 0
    sources: List[str] = []


class QueryPlan(BaseModel):
    """QueryPlanner 的输出：一组搜索查询和并发配置"""
    queries: List[PlannedQuery]
    max_parallel_sources: int = 4
    max_results_per_query: int = 10
    max_fetch_urls: int = 10


# 身份到候选类型的映射
_IDENTITY_MAP = {
    "student_autumn": "校招",
    "student_spring": "校招",
    "student_summer_intern": "实习",
    "student_daily_intern": "实习",
    "working_switch": "社招",
    "working_pivot": "社招",
}


class QueryPlanner:
    """
    根据用户画像生成搜索计划。
    将 profile 中的公司、方向、身份、地区组合成具体的搜索查询。
    """

    MAX_COMPANIES = 5
    MAX_DIRECTIONS = 3
    MAX_QUERIES = 20

    def plan(self, profile: dict) -> QueryPlan:
        companies = self._parse_json_field(profile.get("target_companies", []))[:self.MAX_COMPANIES]
        directions = self._parse_json_field(profile.get("directions", []))[:self.MAX_DIRECTIONS]
        identity = profile.get("identity", "")
        regions = self._parse_json_field(profile.get("regions", []))
        custom_needs = profile.get("custom_needs", "")

        candidate_label = _IDENTITY_MAP.get(identity, "")
        region_str = regions[0] if regions else None
        current_year = str(datetime.utcnow().year - 1)

        queries: List[PlannedQuery] = []
        priority = 0

        # 开放性搜索：公司或方向为空时生成通用查询
        if not companies and not directions:
            queries.append(PlannedQuery(
                query="面经 面试经验",
                priority=priority,
            ))
            priority += 1
            if candidate_label:
                queries.append(PlannedQuery(
                    query=f"{candidate_label} 面经",
                    candidate_type=candidate_label,
                    priority=priority,
                ))
                priority += 1
        elif not companies:
            for direction in directions:
                queries.append(PlannedQuery(
                    query=f"{direction} 面经",
                    position=direction,
                    candidate_type=candidate_label or None,
                    region=region_str,
                    priority=priority,
                ))
                priority += 1
                if candidate_label:
                    queries.append(PlannedQuery(
                        query=f"{direction} {candidate_label} 面经",
                        position=direction,
                        candidate_type=candidate_label,
                        region=region_str,
                        priority=priority,
                    ))
                    priority += 1
        else:
            # candidate_label 片段：如果有（社招/校招/实习），加入搜索词提高精准度
            type_tag = f" {candidate_label}" if candidate_label else ""

            for company in companies:
                if not directions:
                    queries.append(PlannedQuery(
                        query=f"{company}{type_tag} 面经 {current_year}",
                        company=company,
                        candidate_type=candidate_label or None,
                        region=region_str,
                        priority=priority,
                    ))
                    priority += 1
                    queries.append(PlannedQuery(
                        query=f"{company}{type_tag} 面试",
                        company=company,
                        candidate_type=candidate_label or None,
                        region=region_str,
                        priority=priority,
                    ))
                    priority += 1
                    queries.append(PlannedQuery(
                        query=f"{company} 面经",
                        company=company,
                        candidate_type=candidate_label or None,
                        region=region_str,
                        priority=priority,
                    ))
                    priority += 1
                else:
                    for direction in directions:
                        # P0: 公司 + 方向 + 身份 + 面经（最精确）
                        queries.append(PlannedQuery(
                            query=f"{company} {direction}{type_tag} 面经 {current_year}",
                            company=company,
                            position=direction,
                            candidate_type=candidate_label or None,
                            region=region_str,
                            priority=priority,
                        ))
                        priority += 1

                        # P1: 公司 + 方向 + 身份 + 面试
                        queries.append(PlannedQuery(
                            query=f"{company} {direction}{type_tag} 面试",
                            company=company,
                            position=direction,
                            candidate_type=candidate_label or None,
                            region=region_str,
                            priority=priority,
                        ))
                        priority += 1

                        # P2: 公司 + 方向 + 面经（不带身份，兜底）
                        queries.append(PlannedQuery(
                            query=f"{company} {direction} 面经",
                            company=company,
                            position=direction,
                            candidate_type=candidate_label or None,
                            region=region_str,
                            priority=priority,
                        ))
                        priority += 1

                        # P3: 方向 + 身份 + 面经（跨公司，扩大覆盖）
                        queries.append(PlannedQuery(
                            query=f"{direction}{type_tag} 面经 最新",
                            company=None,
                            position=direction,
                            candidate_type=candidate_label or None,
                            region=region_str,
                            priority=priority,
                        ))
                        priority += 1

        queries = queries[:self.MAX_QUERIES]
        queries.sort(key=lambda q: q.priority)

        return QueryPlan(
            queries=queries,
            max_parallel_sources=4,
            max_results_per_query=10,
            max_fetch_urls=10,
        )

    def _parse_json_field(self, value) -> list:
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            import json
            try:
                parsed = json.loads(value)
                return parsed if isinstance(parsed, list) else []
            except (json.JSONDecodeError, TypeError):
                return []
        return []
