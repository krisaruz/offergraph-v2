"""Build JD + interview evidence role profiles."""

from __future__ import annotations

import json
import re
import asyncio
from collections import Counter
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.base import SourceAdapter
from app.config import settings
from app.models.source_document import SourceDocumentModel
from app.runtime.agent_runtime import AgentRuntime
from app.schemas.role_profile import (
    ParsedRoleQuery,
    PreparationAction,
    RoleProfileEvidence,
    RoleProfileResult,
    RoleProfileSearchResponse,
    SkillWeight,
)
from app.services.local_job_radar_cache import LocalJobRadarCache, LocalJobRadarResult


COMPANY_ALIASES: dict[str, tuple[str, ...]] = {
    "阿里巴巴": ("阿里", "阿里巴巴", "alibaba", "千问", "夸克", "通义"),
    "字节跳动": ("字节", "字节跳动", "bytedance", "抖音", "豆包", "seed"),
    "月之暗面": ("kimi", "月之暗面", "moonshot", "moonshot ai"),
}

DIRECTION_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("自动化测试工程师", ("自动化测试", "测试开发", "测开", "qa", "质量保障")),
    ("大模型 Eval 评测", ("大模型eval", "eval", "评测", "模型评估", "模型评价", "agent评测")),
    ("AI 测试开发", ("ai测试", "ai 测试", "大模型测试", "智能测试", "算法测试")),
)

OFFICIAL_JOB_DOMAINS = (
    "jobs.bytedance.com",
    "joinbytedance.com",
    "seed.bytedance.com",
    "careers.alibaba.com",
    "alibabagroup.com",
    "talent-holding.alibaba.com",
    "talent.quark.cn",
    "aidc-jobs.alibaba.com",
    "careers.kimi.com",
    "jobs.ashbyhq.com",
    "moonshot.ai",
)

LOW_VALUE_PATTERNS = re.compile(
    r"(内推|急招|招聘信息|岗位合集|求捞|求offer|offer选择|许愿|薪资|开奖|hc|广告)",
    re.IGNORECASE,
)

INTERVIEW_CUES = re.compile(
    r"(面经|面试|一面|二面|三面|笔试|手撕|追问|八股|项目经历|算法题|系统设计|hr面)",
    re.IGNORECASE,
)

JD_CUES = re.compile(r"(岗位职责|职位描述|任职要求|岗位要求|工作职责|职责|要求|qualification)", re.IGNORECASE)

SKILL_RULES: dict[str, tuple[str, ...]] = {
    "Python/Java/Go 编程基础": ("python", "java", "go", "编码", "语言", "脚本"),
    "测试平台与自动化框架": ("自动化", "测试平台", "pytest", "selenium", "playwright", "工具开发", "平台开发"),
    "接口、数据库与后端基础": ("接口", "api", "http", "数据库", "mysql", "redis", "sql", "服务端"),
    "CI/CD 与质量工程": ("ci", "cd", "流水线", "持续集成", "质量保障", "质量", "效能"),
    "大模型/Agent 评测方法": ("大模型", "llm", "agent", "评测", "评估", "benchmark", "badcase"),
    "数据集与指标设计": ("数据集", "指标", "标注", "一致性", "准确率", "召回", "人工评估"),
    "Prompt/RAG/模型应用理解": ("prompt", "rag", "多模态", "nlp", "模型应用", "上下文"),
    "问题定位与稳定性治理": ("定位", "排查", "稳定性", "鲁棒", "监控", "故障"),
}


class RoleProfileService:
    """Orchestrates runtime search and turns evidence into a role profile."""

    def __init__(self, db: AsyncSession, adapters: dict[str, SourceAdapter]):
        self._db = db
        self._adapters = adapters

    async def search(self, keyword: str, identity: str, regions: list[str] | None = None) -> RoleProfileSearchResponse:
        parsed = self.parse_keyword(keyword)
        runtime_profile = {
            "identity": identity,
            "target_companies": parsed.companies,
            "directions": parsed.directions,
            "regions": regions or [],
            "custom_needs": keyword,
        }
        runtime = AgentRuntime(self._db, self._adapters)
        runtime_result = await runtime.run_search(runtime_profile)
        docs = await self._load_documents(runtime_result.get("items", []))

        evidence = self._collect_evidence(runtime_result.get("items", []), docs, parsed)
        local_cache_result = self._maybe_collect_local_job_cache(parsed, evidence)
        if local_cache_result.evidence:
            evidence = self._merge_evidence(evidence, local_cache_result.evidence)
        profile = await self._build_profile(parsed, evidence)
        sources_status = dict(runtime_result.get("sourcesStatus", {}))
        if local_cache_result.status:
            sources_status["local_job_radar_cache"] = local_cache_result.status

        return RoleProfileSearchResponse(
            sessionId=runtime_result.get("sessionId", ""),
            status=runtime_result.get("status", "failed"),
            parsedQuery=parsed,
            profile=profile,
            sourcesStatus=sources_status,
            searchDuration=runtime_result.get("searchDuration", 0),
            qualityReport={
                **runtime_result.get("qualityReport", {}),
                "roleEvidenceCount": len(evidence),
                "jobEvidenceCount": sum(1 for ev in evidence if ev.evidenceType == "jd_fact"),
                "interviewEvidenceCount": sum(1 for ev in evidence if ev.evidenceType == "interview_evidence"),
                "localJobRadarEvidenceCount": sum(1 for ev in evidence if ev.source == "local_job_radar_cache"),
                "generationMode": "llm" if self._llm_available() else "heuristic",
            },
        )

    @staticmethod
    def parse_keyword(keyword: str) -> ParsedRoleQuery:
        normalized = re.sub(r"\s+", " ", keyword.strip())
        compact = normalized.replace(" ", "").lower()

        companies: list[str] = []
        terms: list[str] = []
        for canonical, aliases in COMPANY_ALIASES.items():
            if any(alias.lower().replace(" ", "") in compact for alias in aliases):
                companies.append(canonical)
                terms.extend(aliases[:3])

        directions: list[str] = []
        for canonical, aliases in DIRECTION_ALIASES:
            if any(alias.lower().replace(" ", "") in compact for alias in aliases):
                directions.append(canonical)
                terms.extend(aliases[:3])

        if not directions:
            cleaned = normalized
            for alias_group in COMPANY_ALIASES.values():
                for alias in alias_group:
                    cleaned = re.sub(re.escape(alias), " ", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"[+的方向岗位工程师]+", " ", cleaned).strip()
            if cleaned:
                directions.append(cleaned)

        return ParsedRoleQuery(
            keyword=keyword,
            companies=companies,
            directions=directions or ["目标岗位"],
            normalizedTerms=sorted(set(t for t in terms if t)),
        )

    async def _load_documents(self, items: list[dict[str, Any]]) -> dict[str, SourceDocumentModel]:
        doc_ids = [item.get("source_document_id") for item in items if item.get("source_document_id")]
        if not doc_ids:
            return {}
        result = await self._db.execute(
            select(SourceDocumentModel).where(SourceDocumentModel.id.in_(doc_ids))
        )
        return {doc.id: doc for doc in result.scalars().all()}

    def _collect_evidence(
        self,
        items: list[dict[str, Any]],
        docs: dict[str, SourceDocumentModel],
        parsed: ParsedRoleQuery,
    ) -> list[RoleProfileEvidence]:
        evidence: list[RoleProfileEvidence] = []
        seen_urls: set[str] = set()

        for item in items:
            source_url = item.get("source_url", "")
            if not source_url or source_url in seen_urls:
                continue
            seen_urls.add(source_url)

            doc = docs.get(item.get("source_document_id"))
            if self._is_job_item(item, doc):
                quote = self._jd_quote(item, doc)
                if quote:
                    evidence.append(RoleProfileEvidence(
                        evidenceType="jd_fact",
                        source=item.get("source", ""),
                        sourceUrl=source_url,
                        title=item.get("title"),
                        quote=quote,
                        confidence=0.92 if item.get("source") == "official_job" else 0.72,
                        publishedAt=item.get("published_at"),
                    ))
                continue

            if not self._is_interview_item(item, doc, parsed):
                continue
            quote = self._interview_quote(item, doc)
            if not quote:
                continue
            limitations = []
            if not item.get("has_full_text"):
                limitations.append("only_snippet_verified")
            evidence.append(RoleProfileEvidence(
                evidenceType="interview_evidence",
                source=item.get("source", ""),
                sourceUrl=source_url,
                title=item.get("title"),
                quote=quote,
                confidence=0.82 if item.get("has_full_text") else 0.58,
                publishedAt=item.get("published_at"),
                limitations=limitations,
            ))

        return evidence[:16]

    def _maybe_collect_local_job_cache(
        self,
        parsed: ParsedRoleQuery,
        evidence: list[RoleProfileEvidence],
    ) -> LocalJobRadarResult:
        live_jd_count = sum(
            1
            for ev in evidence
            if ev.evidenceType == "jd_fact" and ev.source != "local_job_radar_cache"
        )
        target_jd_count = max(1, len(parsed.companies)) if parsed.companies else 1
        if live_jd_count >= target_jd_count:
            return LocalJobRadarResult([])

        cache = LocalJobRadarCache(
            cache_dir=settings.job_radar_cache_dir,
            auto_detect=settings.job_radar_cache_auto_detect,
        )
        return cache.search_evidence(
            company_aliases=self._company_aliases_for(parsed),
            direction_terms=self._direction_terms_for(parsed),
            existing_urls={ev.sourceUrl for ev in evidence},
            limit=max(1, target_jd_count - live_jd_count + 2),
        )

    @staticmethod
    def _merge_evidence(
        primary: list[RoleProfileEvidence],
        extra: list[RoleProfileEvidence],
        limit: int = 16,
    ) -> list[RoleProfileEvidence]:
        by_url: dict[str, RoleProfileEvidence] = {}
        for ev in primary + extra:
            if ev.sourceUrl not in by_url:
                by_url[ev.sourceUrl] = ev
        deduped = list(by_url.values())
        jd = [ev for ev in deduped if ev.evidenceType == "jd_fact"]
        other = [ev for ev in deduped if ev.evidenceType != "jd_fact"]
        return (jd + other)[:limit]

    @staticmethod
    def _company_aliases_for(parsed: ParsedRoleQuery) -> dict[str, tuple[str, ...]]:
        return {
            company: COMPANY_ALIASES.get(company, (company,))
            for company in parsed.companies
        }

    @staticmethod
    def _direction_terms_for(parsed: ParsedRoleQuery) -> list[str]:
        terms = list(parsed.directions)
        for canonical, aliases in DIRECTION_ALIASES:
            if canonical in parsed.directions:
                terms.extend(aliases)
        return terms

    @staticmethod
    def _is_job_item(item: dict[str, Any], doc: SourceDocumentModel | None) -> bool:
        if item.get("source") == "official_job" or (doc and doc.source == "official_job"):
            return True
        host = urlparse(item.get("source_url", "")).netloc.lower()
        return any(domain in host for domain in OFFICIAL_JOB_DOMAINS)

    @staticmethod
    def _is_interview_item(
        item: dict[str, Any],
        doc: SourceDocumentModel | None,
        parsed: ParsedRoleQuery,
    ) -> bool:
        if item.get("source") == "official_job":
            return False

        text = " ".join([
            str(item.get("title") or ""),
            str(item.get("snippet") or ""),
            str(doc.full_text[:800] if doc and doc.full_text else ""),
        ])
        if len(text.strip()) < 12 or LOW_VALUE_PATTERNS.search(text):
            return False
        if item.get("question_count") and item.get("question_count") > 0:
            return True
        if not INTERVIEW_CUES.search(text):
            return False

        company_or_direction = parsed.companies + parsed.directions + parsed.normalizedTerms
        if not company_or_direction:
            return True
        compact_text = text.replace(" ", "").lower()
        return any(term.lower().replace(" ", "") in compact_text for term in company_or_direction)

    @staticmethod
    def _jd_quote(item: dict[str, Any], doc: SourceDocumentModel | None) -> str:
        text = doc.full_text if doc and doc.full_text else item.get("snippet") or item.get("title") or ""
        match = JD_CUES.search(text)
        if match:
            start = max(match.start() - 40, 0)
            return RoleProfileService._clip(text[start:], 260)
        return RoleProfileService._clip(text, 240)

    @staticmethod
    def _interview_quote(item: dict[str, Any], doc: SourceDocumentModel | None) -> str:
        questions = item.get("representative_questions") or []
        if questions:
            texts = [q.get("text", "") for q in questions if isinstance(q, dict) and q.get("text")]
            if texts:
                return "；".join(texts[:3])
        text = doc.full_text if doc and doc.full_text else item.get("snippet") or item.get("title") or ""
        return RoleProfileService._clip(text, 240)

    async def _build_profile(
        self,
        parsed: ParsedRoleQuery,
        evidence: list[RoleProfileEvidence],
    ) -> RoleProfileResult:
        fallback = self._heuristic_profile(parsed, evidence)
        if not self._llm_available() or not evidence:
            return fallback

        llm_payload = await self._try_llm_profile(parsed, evidence)
        if not llm_payload or llm_payload.get("error"):
            return fallback

        try:
            return self._merge_llm_profile(parsed, evidence, fallback, llm_payload)
        except Exception:
            return fallback

    def _heuristic_profile(
        self,
        parsed: ParsedRoleQuery,
        evidence: list[RoleProfileEvidence],
    ) -> RoleProfileResult:
        jd_count = sum(1 for ev in evidence if ev.evidenceType == "jd_fact")
        local_jd_count = sum(1 for ev in evidence if ev.source == "local_job_radar_cache")
        live_jd_count = jd_count - local_jd_count
        interview_count = sum(1 for ev in evidence if ev.evidenceType == "interview_evidence")
        confidence = "high" if live_jd_count >= 1 and interview_count >= 3 else ("medium" if evidence else "low")

        skill_weights = self._skill_weights(evidence, parsed)
        scenarios = self._business_scenarios(evidence, parsed)
        focus = self._interview_focus(evidence, skill_weights, parsed)
        prep = self._preparation_plan(skill_weights, jd_count, interview_count, live_jd_count)
        limitations = []
        if jd_count == 0:
            limitations.append("缺少官网 JD 证据，岗位职责和业务场景只能低置信推断")
        elif local_jd_count and live_jd_count == 0:
            limitations.append("当前 JD 证据来自本地 JobRadar 快照，未实时校验岗位是否仍在招")
        elif local_jd_count:
            limitations.append("部分 JD 证据来自本地 JobRadar 快照，实时性低于官网在线结果")
        if interview_count < 3:
            limitations.append("近期高质量面经不足 3 条，面试重点统计置信度偏低")

        company_text = "、".join(parsed.companies) if parsed.companies else "目标公司"
        direction = " / ".join(parsed.directions)
        summary = (
            f"{company_text} 的 {direction} 画像基于 {jd_count} 条 JD 证据和 "
            f"{interview_count} 条面经证据生成。重点关注 "
            f"{'、'.join([s.skill for s in skill_weights[:3]]) or '岗位相关基础能力'}。"
        )

        return RoleProfileResult(
            targetRole=f"{company_text}｜{direction}",
            companies=parsed.companies,
            direction=direction,
            confidence=confidence,
            roleSummary=summary,
            businessScenarios=scenarios,
            skillWeights=skill_weights,
            interviewFocus=focus,
            preparationPlan=prep,
            evidence=evidence,
            evidenceStats={
                "jobPostingCount": jd_count,
                "liveJobPostingCount": live_jd_count,
                "localJobRadarEvidenceCount": local_jd_count,
                "interviewEvidenceCount": interview_count,
                "sourceCount": len({ev.source for ev in evidence}),
                "highConfidenceEvidenceCount": sum(1 for ev in evidence if ev.confidence >= 0.8),
            },
            limitations=limitations,
        )

    def _skill_weights(
        self,
        evidence: list[RoleProfileEvidence],
        parsed: ParsedRoleQuery,
    ) -> list[SkillWeight]:
        text = "\n".join(f"{ev.title or ''}\n{ev.quote or ''}" for ev in evidence).lower()
        counts: Counter[str] = Counter()
        reasons: dict[str, str] = {}
        for skill, terms in SKILL_RULES.items():
            hit_count = sum(text.count(term.lower()) for term in terms)
            if hit_count:
                counts[skill] = hit_count
                reasons[skill] = f"证据中命中 {hit_count} 次相关关键词：{', '.join(terms[:3])}"

        compact_directions = " ".join(parsed.directions).lower()
        if "eval" in compact_directions or "评测" in compact_directions:
            counts["大模型/Agent 评测方法"] += 3
            counts["数据集与指标设计"] += 2
        if "测试" in compact_directions:
            counts["测试平台与自动化框架"] += 3
            counts["接口、数据库与后端基础"] += 2

        if not counts:
            counts["岗位相关基础能力"] = 1

        total = sum(counts.values())
        ranked = counts.most_common(6)
        return [
            SkillWeight(
                skill=skill,
                weight=round(score / total, 2),
                evidenceCount=score,
                reason=reasons.get(skill, "由岗位方向和证据关键词共同推断"),
            )
            for skill, score in ranked
        ]

    @staticmethod
    def _business_scenarios(
        evidence: list[RoleProfileEvidence],
        parsed: ParsedRoleQuery,
    ) -> list[str]:
        text = "\n".join(f"{ev.title or ''} {ev.quote or ''}" for ev in evidence)
        scenarios = []
        for token, scenario in [
            ("豆包", "豆包/AI 助手类产品质量保障与评测"),
            ("抖音", "内容平台或推荐/搜索场景下的质量工程"),
            ("飞书", "企业协作与 Agent 应用平台测试"),
            ("Seed", "模型团队相关 AI 应用或算法质量验证"),
            ("Kimi", "Kimi/Moonshot 大模型产品的效果评测与 badcase 分析"),
            ("Moonshot", "Moonshot 大模型产品的效果评测与 badcase 分析"),
            ("Agent", "Agent 工具链、任务成功率和多轮交互质量评估"),
            ("大模型", "大模型应用效果、稳定性和安全边界评测"),
        ]:
            if token.lower() in text.lower() or token.lower() in " ".join(parsed.normalizedTerms).lower():
                scenarios.append(scenario)
        if not scenarios:
            scenarios.append("围绕目标岗位的业务质量、工程效率和面试问题沉淀")
        return list(dict.fromkeys(scenarios))[:5]

    @staticmethod
    def _interview_focus(
        evidence: list[RoleProfileEvidence],
        skill_weights: list[SkillWeight],
        parsed: ParsedRoleQuery,
    ) -> list[str]:
        interview_quotes = [ev.quote for ev in evidence if ev.evidenceType == "interview_evidence" and ev.quote]
        focus = []
        for quote in interview_quotes[:5]:
            focus.append(RoleProfileService._clip(quote, 120))
        if len(focus) < 3:
            for skill in skill_weights[:4]:
                focus.append(f"围绕 {skill.skill} 准备可追问的项目案例和技术细节")
        if any("评测" in d or "Eval" in d for d in parsed.directions):
            focus.append("准备如何设计评测集、指标、人工验收和 badcase 归因的完整闭环")
        return list(dict.fromkeys(focus))[:6]

    @staticmethod
    def _preparation_plan(
        skill_weights: list[SkillWeight],
        jd_count: int,
        interview_count: int,
        live_jd_count: int,
    ) -> list[PreparationAction]:
        plan = [
            PreparationAction(
                priority="P0",
                action=f"用 2 个项目故事串起 {skill_weights[0].skill if skill_weights else '核心能力'}：背景、方案、指标、结果和复盘",
                reason="岗位画像中权重最高的能力通常会被从项目经历和技术实现两侧追问",
            ),
            PreparationAction(
                priority="P0",
                action="整理 10 道真实高频问题的标准回答，每题包含原理、落地方案、边界和踩坑",
                reason="面经证据需要转化成可回答的问题库，而不是只看关键词",
            ),
            PreparationAction(
                priority="P1",
                action="准备一份 JD 对照表：职责/要求逐条映射到自己的项目证据",
                reason="官网 JD 是岗位画像的一等证据，面试时常用于判断岗位匹配度",
            ),
        ]
        if jd_count == 0 or live_jd_count == 0:
            plan.append(PreparationAction(
                priority="P1",
                action="补采或核验实时官网 JD，再更新岗位职责和技能权重",
                reason="缺少实时官网 JD 会让岗位职责判断依赖缓存或面经样本",
            ))
        if interview_count < 3:
            plan.append(PreparationAction(
                priority="P1",
                action="继续补采近期牛客/小红书/脉脉面经，优先选择有具体问题和日期的帖子",
                reason="近期真实问题不足会让面试重点统计不稳定",
            ))
        return plan

    async def _try_llm_profile(
        self,
        parsed: ParsedRoleQuery,
        evidence: list[RoleProfileEvidence],
    ) -> dict[str, Any] | None:
        from app.llm.client import llm_client

        evidence_payload = [ev.model_dump() for ev in evidence[:12]]
        messages = [
            {
                "role": "system",
                "content": (
                    "你是岗位画像分析器。只能使用输入 evidence 中的信息，"
                    "不得把推断伪装成 JD 或真实面经。输出合法 JSON。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps({
                    "parsedQuery": parsed.model_dump(),
                    "evidence": evidence_payload,
                    "requiredSchema": {
                        "roleSummary": "string",
                        "businessScenarios": ["string"],
                        "skillWeights": [{"skill": "string", "weight": 0.3, "reason": "string"}],
                        "interviewFocus": ["string"],
                        "preparationPlan": [{"priority": "P0", "action": "string", "reason": "string"}],
                        "limitations": ["string"],
                    },
                }, ensure_ascii=False),
            },
        ]
        try:
            return await asyncio.wait_for(
                llm_client.chat_json(messages, temperature=0.1, max_tokens=2400),
                timeout=settings.role_profile_llm_timeout,
            )
        except asyncio.TimeoutError:
            return {"error": "role_profile_llm_timeout", "confidence": 0}

    @staticmethod
    def _merge_llm_profile(
        parsed: ParsedRoleQuery,
        evidence: list[RoleProfileEvidence],
        fallback: RoleProfileResult,
        payload: dict[str, Any],
    ) -> RoleProfileResult:
        skill_payload = payload.get("skillWeights") or []
        skills = []
        for item in skill_payload[:6]:
            if not isinstance(item, dict) or not item.get("skill"):
                continue
            skills.append(SkillWeight(
                skill=str(item.get("skill")),
                weight=float(item.get("weight") or 0),
                evidenceCount=int(item.get("evidenceCount") or 0),
                reason=str(item.get("reason") or "LLM 基于证据归纳"),
            ))

        prep_payload = payload.get("preparationPlan") or []
        prep = []
        for item in prep_payload[:8]:
            if not isinstance(item, dict) or not item.get("action"):
                continue
            prep.append(PreparationAction(
                priority=str(item.get("priority") or "P1"),
                action=str(item.get("action")),
                reason=str(item.get("reason") or "基于证据归纳"),
            ))

        return fallback.model_copy(update={
            "roleSummary": str(payload.get("roleSummary") or fallback.roleSummary),
            "businessScenarios": payload.get("businessScenarios") or fallback.businessScenarios,
            "skillWeights": skills or fallback.skillWeights,
            "interviewFocus": payload.get("interviewFocus") or fallback.interviewFocus,
            "preparationPlan": prep or fallback.preparationPlan,
            "limitations": payload.get("limitations") or fallback.limitations,
        })

    @staticmethod
    def _llm_available() -> bool:
        return bool(settings.llm_api_base and settings.llm_api_key)

    @staticmethod
    def _clip(text: str, max_len: int) -> str:
        compact = re.sub(r"\s+", " ", text or "").strip()
        return compact[:max_len]
