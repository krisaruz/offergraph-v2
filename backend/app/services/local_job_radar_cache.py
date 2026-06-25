"""Read local ai-job-radar official job snapshots as a JD fallback."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.schemas.role_profile import RoleProfileEvidence


LOCAL_OFFICIAL_PLATFORMS = {
    "alibaba",
    "antgroup",
    "baidu",
    "bytedance",
    "didi",
    "huawei",
    "jd",
    "kuaishou",
    "meituan",
    "netease",
    "quark",
    "tencent",
    "xiaohongshu",
}


@dataclass(frozen=True)
class LocalJobRadarResult:
    evidence: list[RoleProfileEvidence]
    status: dict[str, Any] | None = None


class LocalJobRadarCache:
    """Turns ai-job-radar normalized job snapshots into low-priority JD evidence.

    The cache is a recovery path for environments where live official JD discovery
    is temporarily unavailable. It intentionally marks evidence as a local
    snapshot so downstream summaries do not present it as a freshly verified JD.
    """

    def __init__(self, cache_dir: str = "", auto_detect: bool = True):
        self._configured_dir = cache_dir.strip()
        self._auto_detect = auto_detect

    def search_evidence(
        self,
        *,
        company_aliases: dict[str, tuple[str, ...]],
        direction_terms: list[str],
        existing_urls: set[str],
        limit: int = 6,
    ) -> LocalJobRadarResult:
        root = self._resolve_root()
        if root is None:
            if self._configured_dir:
                return LocalJobRadarResult([], self._status(
                    "config_error",
                    f"JOB_RADAR_CACHE_DIR does not exist: {self._configured_dir}",
                    recoverable=True,
                    next_action="configure",
                ))
            return LocalJobRadarResult([], None)

        files = self._candidate_files(root)
        if not files:
            return LocalJobRadarResult([], self._status(
                "empty",
                "No JobRadar cache JSON files found",
                recoverable=True,
                next_action="refresh_cache",
            ))

        postings: list[dict[str, Any]] = []
        parse_errors: list[str] = []
        for path in files:
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                parse_errors.append(f"{path.name}: {exc}")
                continue
            if isinstance(loaded, list):
                postings.extend(item for item in loaded if isinstance(item, dict))

        if not postings and parse_errors:
            return LocalJobRadarResult([], self._status(
                "error",
                "; ".join(parse_errors[:2]),
                recoverable=True,
                next_action="refresh_cache",
            ))
        if not postings:
            return LocalJobRadarResult([], self._status(
                "empty",
                "JobRadar cache contains no job postings",
                recoverable=True,
                next_action="refresh_cache",
            ))

        scored: list[tuple[str, int, RoleProfileEvidence]] = []
        seen_urls = set(existing_urls)
        normalized_direction_terms = self._normalize_terms(direction_terms)
        for job in postings:
            url = str(job.get("url") or "").strip()
            if not url or url in seen_urls:
                continue
            if not self._looks_like_official_snapshot(job):
                continue

            matched_company = self._matched_company(job, company_aliases)
            if company_aliases and not matched_company:
                continue

            score = self._score_job(job, normalized_direction_terms)
            if score <= 0:
                continue

            quote = self._build_quote(job)
            if not quote:
                continue

            seen_urls.add(url)
            scored.append((
                matched_company,
                score,
                RoleProfileEvidence(
                    evidenceType="jd_fact",
                    source="local_job_radar_cache",
                    sourceUrl=url,
                    title=str(job.get("title") or "本地 JobRadar 岗位快照"),
                    quote=quote,
                    confidence=0.76,
                    publishedAt=str(job.get("publish_date") or job.get("scraped_at") or "") or None,
                    limitations=["local_snapshot", "not_live_verified"],
                ),
            ))

        evidence = self._select_balanced_evidence(scored, limit)
        if evidence:
            return LocalJobRadarResult(evidence, self._status(
                "ok",
                None,
                recoverable=True,
                next_action="none",
                count=len(evidence),
            ))

        return LocalJobRadarResult([], self._status(
            "empty",
            "No JobRadar cache postings matched target company and direction",
            recoverable=True,
            next_action="refresh_cache",
        ))

    def _resolve_root(self) -> Path | None:
        if self._configured_dir:
            configured = Path(self._configured_dir).expanduser()
            return configured if configured.exists() else None
        if not self._auto_detect:
            return None
        detected = Path.home() / "Desktop" / "ai-job-radar"
        return detected if detected.exists() else None

    @staticmethod
    def _candidate_files(root: Path) -> list[Path]:
        data_dir = root / "data"
        candidates: list[Path] = []
        jobs_json = data_dir / "jobs.json"
        if jobs_json.exists() and jobs_json.stat().st_size > 2:
            candidates.append(jobs_json)

        daily_dir = data_dir / "daily"
        if daily_dir.exists():
            daily_files = sorted(
                (
                    path for path in daily_dir.glob("*.json")
                    if not path.name.endswith("_raw.json") and path.stat().st_size > 2
                ),
                key=lambda path: path.stat().st_mtime,
                reverse=True,
            )
            candidates.extend(path for path in daily_files if path not in candidates)

        return candidates[:4]

    @staticmethod
    def _looks_like_official_snapshot(job: dict[str, Any]) -> bool:
        platform = str(job.get("platform") or "").lower()
        if platform in LOCAL_OFFICIAL_PLATFORMS:
            return True

        url = str(job.get("url") or "").lower()
        return any(
            domain in url
            for domain in (
                "careers.",
                "jobs.",
                "jobdesc.html",
                "talent.",
                "joinbytedance.com",
                "ashbyhq.com",
            )
        )

    @staticmethod
    def _score_job(
        job: dict[str, Any],
        direction_terms: list[str],
    ) -> int:
        title = str(job.get("title") or "")
        category = str(job.get("category") or "")
        text = " ".join(
            str(job.get(field) or "")
            for field in (
                "company",
                "platform",
                "title",
                "department",
                "location",
                "category",
                "description",
                "requirements",
                "url",
            )
        )
        compact_text = LocalJobRadarCache._compact(text)

        direction_score = 0
        compact_title = LocalJobRadarCache._compact(title)
        compact_category = LocalJobRadarCache._compact(category)
        for term in direction_terms:
            compact_term = LocalJobRadarCache._compact(term)
            if len(compact_term) < 2:
                continue
            if compact_term in compact_title:
                direction_score += 4
            elif compact_term in compact_category:
                direction_score += 3
            elif compact_term in compact_text:
                direction_score += 1

        if direction_score <= 0:
            return 0

        richness = 1 if len(str(job.get("description") or "")) >= 60 else 0
        return direction_score + richness

    @staticmethod
    def _matched_company(
        job: dict[str, Any],
        company_aliases: dict[str, tuple[str, ...]],
    ) -> str:
        if not company_aliases:
            return ""

        text = " ".join(
            str(job.get(field) or "")
            for field in ("company", "platform", "title", "department", "description", "url")
        )
        compact_text = LocalJobRadarCache._compact(text)
        for company, aliases in company_aliases.items():
            if any(LocalJobRadarCache._compact(alias) in compact_text for alias in aliases):
                return company
        return ""

    @staticmethod
    def _select_balanced_evidence(
        scored: list[tuple[str, int, RoleProfileEvidence]],
        limit: int,
    ) -> list[RoleProfileEvidence]:
        ordered = sorted(scored, key=lambda item: item[1], reverse=True)
        selected: list[tuple[str, int, RoleProfileEvidence]] = []
        selected_urls: set[str] = set()

        for company in dict.fromkeys(company for company, _, _ in ordered if company):
            for item in ordered:
                item_company, _, evidence = item
                if item_company == company and evidence.sourceUrl not in selected_urls:
                    selected.append(item)
                    selected_urls.add(evidence.sourceUrl)
                    break
            if len(selected) >= limit:
                break

        for item in ordered:
            if len(selected) >= limit:
                break
            evidence = item[2]
            if evidence.sourceUrl in selected_urls:
                continue
            selected.append(item)
            selected_urls.add(evidence.sourceUrl)

        return [item[2] for item in selected[:limit]]

    @staticmethod
    def _build_quote(job: dict[str, Any]) -> str:
        parts = [
            f"岗位：{job.get('title')}",
            f"公司：{job.get('company')}",
        ]
        department = str(job.get("department") or "").strip()
        if department:
            parts.append(f"部门：{department}")
        location = str(job.get("location") or "").strip()
        if location:
            parts.append(f"地点：{location}")

        body = "\n".join(
            str(job.get(field) or "").strip()
            for field in ("description", "requirements")
            if str(job.get(field) or "").strip()
        )
        if body:
            parts.append(f"职责/要求：{LocalJobRadarCache._clip(body, 280)}")
        return "｜".join(part for part in parts if part and part != "岗位：None" and part != "公司：None")

    @staticmethod
    def _normalize_terms(terms: list[str]) -> list[str]:
        deduped: list[str] = []
        seen: set[str] = set()
        for term in terms:
            compact = LocalJobRadarCache._compact(term)
            if not compact or compact in seen:
                continue
            seen.add(compact)
            deduped.append(term)
        return deduped

    @staticmethod
    def _compact(text: str) -> str:
        return re.sub(r"\s+", "", text or "").lower()

    @staticmethod
    def _clip(text: str, max_len: int) -> str:
        compact = re.sub(r"\s+", " ", text or "").strip()
        return compact[:max_len]

    @staticmethod
    def _status(
        status: str,
        reason: str | None,
        *,
        recoverable: bool,
        next_action: str,
        count: int = 0,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "reason": reason,
            "recoverable": recoverable,
            "nextAction": next_action,
            "count": count,
        }
