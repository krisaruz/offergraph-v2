"""Deterministic interview-intent checks used before expensive LLM work."""

from __future__ import annotations

import json
import re
from typing import Any

GENERIC_SEARCH_SOURCES = {"search_engine", "web"}

COMPANY_ALIASES: dict[str, tuple[str, ...]] = {
    "阿里巴巴": ("阿里", "阿里巴巴", "alibaba", "阿里云", "千问", "夸克", "通义"),
    "字节跳动": ("字节", "字节跳动", "bytedance", "抖音", "豆包", "seed"),
    "月之暗面": ("kimi", "月之暗面", "moonshot", "moonshotai", "moonshot ai"),
    "腾讯": ("腾讯", "tencent", "腾讯云"),
    "百度": ("百度", "baidu"),
    "小红书": ("小红书", "xhs", "rednote"),
}

INTERVIEW_INTENT_KEYWORDS = (
    "面经",
    "面试",
    "面试题",
    "面试官",
    "面试经验",
    "笔试",
    "一面",
    "二面",
    "三面",
    "hr面",
    "hr 面",
    "终面",
    "offer",
    "oc",
    "手撕",
    "八股",
    "反问",
    "interview",
    "interview question",
    "interview questions",
    "phone screen",
    "onsite",
)

SHORT_TOKEN_KEYWORDS = {"oc"}


def _compact(text: str | None) -> str:
    return re.sub(r"\s+", "", (text or "").lower())


def target_companies_from_profile(profile: dict[str, Any] | None) -> list[str]:
    if not profile:
        return []

    companies = profile.get("target_companies", [])
    if isinstance(companies, str):
        try:
            parsed = json.loads(companies)
            companies = parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, TypeError):
            companies = []
    if not isinstance(companies, list):
        return []
    return [str(company).strip() for company in companies if str(company).strip()]


def target_company_aliases(target_companies: list[str] | tuple[str, ...] | None) -> set[str]:
    aliases: set[str] = set()
    if not target_companies:
        return aliases

    known_groups = {
        _compact(canonical): {_compact(canonical), *(_compact(alias) for alias in group)}
        for canonical, group in COMPANY_ALIASES.items()
    }

    for company in target_companies:
        compact = _compact(str(company))
        if not compact:
            continue
        aliases.add(compact)
        for group in known_groups.values():
            if compact in group:
                aliases.update(alias for alias in group if alias)
                break

    return aliases


def candidate_matches_target_company(
    item: dict[str, Any],
    target_companies: list[str] | tuple[str, ...] | None,
) -> bool:
    """Return whether a candidate mentions one of the requested companies."""
    aliases = target_company_aliases(target_companies)
    if not aliases:
        return True

    strong_parts = [
        str(item.get(field) or "")
        for field in ("title", "source_url", "company")
    ]
    raw = item.get("raw")
    if isinstance(raw, dict):
        strong_parts.extend(
            str(raw.get(field) or "")
            for field in ("title", "company")
        )

    strong_text = _compact(" ".join(strong_parts))
    return any(alias and alias in strong_text for alias in aliases)


def has_interview_signal(text: str | None) -> bool:
    normalized = (text or "").lower()
    for keyword in INTERVIEW_INTENT_KEYWORDS:
        lowered = keyword.lower()
        if lowered in SHORT_TOKEN_KEYWORDS:
            if re.search(rf"(?<![a-z0-9]){re.escape(lowered)}(?![a-z0-9])", normalized):
                return True
            continue
        if lowered in normalized:
            return True
    return False


def should_keep_search_candidate(item: dict[str, Any]) -> bool:
    """Return whether a search candidate is allowed to enter the interview Feed."""
    source = str(item.get("source") or "")
    if source not in GENERIC_SEARCH_SOURCES:
        return True

    text = " ".join(
        str(item.get(field) or "")
        for field in ("title", "snippet", "source_url")
    )
    return has_interview_signal(text)


def has_extractable_interview_content(
    *,
    title: str | None = None,
    full_text: str | None = None,
) -> bool:
    text = f"{title or ''}\n{full_text or ''}"
    return has_interview_signal(text)
