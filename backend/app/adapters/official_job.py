"""
公司官网 JD 适配器。

本适配器通过自托管 SearXNG 发现公司官方招聘页，不直接接入付费 API，
也不把第三方招聘搬运站当作官方 JD。它先服务于岗位画像的证据入口：
搜索结果仍复用 SourceSearchItem，以便现有 Runtime 无需数据库迁移即可聚合。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from json import JSONDecodeError
from typing import List, Optional
from urllib.parse import urljoin, urlparse

import httpx

from app.adapters.base import (
    SourceAdapter,
    SourceDocument,
    SourceQuery,
    SourceSearchItem,
    SourceSearchResult,
    SourceStatus,
)
from app.adapters.free_web_search import search_bing_rss
from app.config import settings
from app.utils.text_clean import clean_html, content_hash, normalize_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OfficialCompanySource:
    canonical: str
    aliases: tuple[str, ...]
    domains: tuple[str, ...]


OFFICIAL_COMPANY_SOURCES: tuple[OfficialCompanySource, ...] = (
    OfficialCompanySource(
        canonical="字节跳动",
        aliases=("字节", "字节跳动", "bytedance", "抖音", "豆包", "seed"),
        domains=("jobs.bytedance.com", "joinbytedance.com", "seed.bytedance.com"),
    ),
    OfficialCompanySource(
        canonical="阿里巴巴",
        aliases=("阿里", "阿里巴巴", "alibaba", "千问", "夸克", "通义"),
        domains=(
            "careers.alibaba.com",
            "www.alibabagroup.com/careers",
            "talent-holding.alibaba.com",
            "talent.quark.cn",
            "aidc-jobs.alibaba.com",
        ),
    ),
    OfficialCompanySource(
        canonical="月之暗面",
        aliases=("kimi", "月之暗面", "moonshot", "moonshot ai"),
        domains=("careers.kimi.com", "jobs.ashbyhq.com/moonshot-ai", "www.moonshot.ai"),
    ),
)

JOB_INTENT_WORDS = (
    "招聘",
    "岗位",
    "职位",
    "jd",
    "职责",
    "要求",
    "任职",
    "测试",
    "开发",
    "eval",
    "评测",
    "评估",
    "job",
    "jobs",
    "career",
    "careers",
    "position",
    "positions",
    "open positions",
    "opportunities",
)

INTERVIEW_NOISE_WORDS = ("面经", "面试经验", "一面", "二面", "三面", "笔试")


class OfficialJobAdapter(SourceAdapter):
    id = "official_job"
    display_name = "公司官网 JD"

    @property
    def capabilities(self) -> dict:
        return {
            "search": True,
            "fetchDetail": True,
            "requiresLogin": False,
            "supportsDateFilter": False,
        }

    async def search(self, query: SourceQuery) -> SourceSearchResult:
        start_time = datetime.utcnow()

        if not settings.official_job_enabled:
            return SourceSearchResult(
                source=self.id,
                status=SourceStatus.DISABLED,
                reason="Disabled in settings",
                duration_ms=0.0,
            )
        provider_was_explicit = "search_api_provider" in settings.model_fields_set
        if provider_was_explicit and settings.search_api_provider != "searxng":
            return SourceSearchResult(
                source=self.id,
                status=SourceStatus.CONFIG_ERROR,
                reason="Only free self-hosted SearXNG is supported for official JD search",
                duration_ms=0.0,
            )

        sources = self._match_company_sources(query)
        if not sources:
            return SourceSearchResult(
                source=self.id,
                status=SourceStatus.EMPTY,
                reason="No supported official job source matched query company",
                duration_ms=self._elapsed_ms(start_time),
            )

        use_searxng = bool(settings.searxng_base_url)
        timeout = httpx.Timeout(settings.search_timeout_search_engine)
        results: list[SourceSearchItem] = []
        status = SourceStatus.OK
        reason = None

        try:
            if use_searxng:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    for company_source in sources:
                        for domain in company_source.domains[:3]:
                            data = await self._search_domain(client, query, company_source, domain)
                            if isinstance(data, SourceSearchResult):
                                if status != SourceStatus.OK:
                                    continue
                                status = data.status
                                reason = data.reason
                                continue

                            for item in data:
                                parsed = self._parse_result(item, company_source)
                                if parsed:
                                    results.append(parsed)
                                if len(results) >= query.limit:
                                    break
                            if len(results) >= query.limit:
                                break
                        if len(results) >= query.limit:
                            break
            else:
                logger.info("OfficialJob: SEARXNG_BASE_URL is missing, using free Bing RSS fallback")
                for company_source in sources:
                    for domain in company_source.domains[:3]:
                        data = await self._search_domain_free(query, company_source, domain)
                        if isinstance(data, SourceSearchResult):
                            if status != SourceStatus.OK:
                                continue
                            status = data.status
                            reason = data.reason
                            continue

                        for item in data:
                            parsed = self._parse_result(item, company_source)
                            if parsed:
                                results.append(parsed)
                            if len(results) >= query.limit:
                                break
                        if len(results) >= query.limit:
                            break
                    if len(results) >= query.limit:
                        break

            results = self._dedupe_results(results)[:query.limit]
            if results:
                status = SourceStatus.OK
                reason = None if use_searxng else "SEARXNG_BASE_URL missing; used free Bing RSS fallback"
            elif status == SourceStatus.OK:
                status = SourceStatus.EMPTY
                reason = "No official JD results matched query"

        except httpx.TimeoutException:
            logger.warning("OfficialJob search timeout")
            status = SourceStatus.TIMEOUT
            reason = (
                "Timeout calling SearXNG API for official JD search"
                if use_searxng
                else "Timeout calling free Bing RSS fallback for official JD search"
            )
        except Exception as exc:
            logger.error("OfficialJob search error: %s", exc)
            status = SourceStatus.ERROR
            reason = str(exc)

        return SourceSearchResult(
            source=self.id,
            status=status,
            items=results,
            count=len(results),
            reason=reason,
            duration_ms=self._elapsed_ms(start_time),
        )

    async def fetch(self, url: str) -> Optional[SourceDocument]:
        """抓取官方 JD 页面正文，供后续岗位画像模块提取职责/要求。"""
        if not self._is_known_official_url(url):
            return None

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml",
        }
        timeout = httpx.Timeout(settings.webfetch_timeout)

        try:
            async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None
                content_type = resp.headers.get("content-type", "")
                if "text/html" not in content_type and "text/plain" not in content_type:
                    return None

                html = resp.text
                text = normalize_text(clean_html(html))
                if not text or len(text) < 50:
                    return None

                return SourceDocument(
                    source=self.id,
                    source_url=str(resp.url),
                    title=self._extract_title(html),
                    full_text=text,
                    content_hash=content_hash(text),
                    raw={"evidence_type": "jd_fact", "source_reliability": "official"},
                )
        except Exception as exc:
            logger.warning("OfficialJob fetch failed: %s - %s", url, exc)
            return None

    async def _search_domain(
        self,
        client: httpx.AsyncClient,
        query: SourceQuery,
        company_source: OfficialCompanySource,
        domain: str,
    ) -> list[dict] | SourceSearchResult:
        params = {
            "q": self._build_search_query(query, company_source, domain),
            "format": "json",
            "language": settings.searxng_language,
            "safesearch": settings.searxng_safe_search,
            "pageno": 1,
        }
        search_url = urljoin(settings.searxng_base_url.rstrip("/") + "/", "search")
        resp = await client.get(search_url, params=params)

        if resp.status_code == 403:
            return SourceSearchResult(
                source=self.id,
                status=SourceStatus.CONFIG_ERROR,
                reason="SearXNG JSON format is disabled or forbidden",
            )
        if resp.status_code == 429:
            return SourceSearchResult(
                source=self.id,
                status=SourceStatus.RATE_LIMITED,
                reason="Rate limited by SearXNG",
            )
        if resp.status_code != 200:
            return SourceSearchResult(
                source=self.id,
                status=SourceStatus.ERROR,
                reason=f"HTTP Error {resp.status_code}",
            )

        try:
            payload = resp.json()
        except JSONDecodeError:
            return SourceSearchResult(
                source=self.id,
                status=SourceStatus.CONFIG_ERROR,
                reason="SearXNG did not return JSON; enable search.formats=json",
            )

        return payload.get("results", [])

    async def _search_domain_free(
        self,
        query: SourceQuery,
        company_source: OfficialCompanySource,
        domain: str,
    ) -> list[dict] | SourceSearchResult:
        outcome = await search_bing_rss(
            self._build_search_query(query, company_source, domain),
            limit=query.limit,
            timeout_s=settings.search_timeout_search_engine,
            language=settings.searxng_language,
        )
        if outcome.status == SourceStatus.OK:
            return outcome.results
        return SourceSearchResult(
            source=self.id,
            status=outcome.status,
            reason=outcome.reason,
        )

    def _build_search_query(
        self,
        query: SourceQuery,
        company_source: OfficialCompanySource,
        domain: str,
    ) -> str:
        direction = self._job_direction(query)
        terms = [company_source.canonical, direction, "招聘", "岗位", "职责", "任职要求"]
        compact_terms = " ".join(term for term in terms if term)
        return f"{compact_terms} site:{domain}"

    def _parse_result(
        self,
        item: dict,
        company_source: OfficialCompanySource,
    ) -> Optional[SourceSearchItem]:
        link = item.get("url") or item.get("link") or ""
        if not link or not self._matches_official_source(link, company_source):
            return None

        title = item.get("title") or link
        snippet = item.get("content") or item.get("snippet") or ""
        if not self._looks_like_job_result(title, snippet, link):
            return None

        return SourceSearchItem(
            source=self.id,
            source_url=link,
            title=title,
            snippet=snippet,
            published_at=item.get("publishedDate") or item.get("published_at") or item.get("date"),
            raw={
                **item,
                "company": company_source.canonical,
                "evidence_type": "jd_fact",
                "source_reliability": "official",
            },
        )

    @staticmethod
    def _dedupe_results(items: list[SourceSearchItem]) -> list[SourceSearchItem]:
        seen: set[str] = set()
        deduped: list[SourceSearchItem] = []
        for item in items:
            if item.source_url in seen:
                continue
            seen.add(item.source_url)
            deduped.append(item)
        return deduped

    @staticmethod
    def _elapsed_ms(start_time: datetime) -> float:
        return float(int((datetime.utcnow() - start_time).total_seconds() * 1000))

    @staticmethod
    def _job_direction(query: SourceQuery) -> str:
        raw = query.position or query.query
        text = raw or ""
        for noise in INTERVIEW_NOISE_WORDS:
            text = text.replace(noise, " ")
        text = re.sub(r"\s+", " ", text).strip()
        return text[:80]

    @staticmethod
    def _match_company_sources(query: SourceQuery) -> list[OfficialCompanySource]:
        text = f"{query.company or ''} {query.query or ''}".lower()
        matches: list[OfficialCompanySource] = []
        for source in OFFICIAL_COMPANY_SOURCES:
            if any(alias.lower() in text for alias in source.aliases):
                matches.append(source)
        return matches

    @staticmethod
    def _looks_like_job_result(title: str, snippet: str, link: str) -> bool:
        text = f"{title} {snippet} {link}".lower()
        return any(word.lower() in text for word in JOB_INTENT_WORDS)

    @staticmethod
    def _matches_official_source(url: str, source: OfficialCompanySource) -> bool:
        return any(OfficialJobAdapter._matches_domain_or_path(url, domain) for domain in source.domains)

    @staticmethod
    def _is_known_official_url(url: str) -> bool:
        return any(
            OfficialJobAdapter._matches_domain_or_path(url, domain)
            for source in OFFICIAL_COMPANY_SOURCES
            for domain in source.domains
        )

    @staticmethod
    def _matches_domain_or_path(url: str, domain_or_path: str) -> bool:
        parsed = urlparse(url)
        host = parsed.netloc.lower()
        path = parsed.path.lower().lstrip("/")
        target = domain_or_path.lower().lstrip("/")
        if "/" in target:
            target_host, target_path = target.split("/", 1)
            return (
                (host == target_host or host.endswith("." + target_host))
                and path.startswith(target_path)
            )
        return host == target or host.endswith("." + target)

    @staticmethod
    def _extract_title(html: str) -> Optional[str]:
        match = re.search(r"<title>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return None
        return normalize_text(match.group(1))[:100]
