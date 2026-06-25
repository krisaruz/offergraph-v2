from __future__ import annotations

import asyncio
import json
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

import app.services.role_profile_service as role_profile_module
from app.services.role_profile_service import RoleProfileService
from app.schemas.role_profile import RoleProfileEvidence


def test_role_profile_parser_handles_alibaba_bytedance_automation_testing():
    parsed = RoleProfileService.parse_keyword("阿里+字节的自动化测试工程师")

    assert parsed.companies == ["阿里巴巴", "字节跳动"]
    assert "自动化测试工程师" in parsed.directions


def test_role_profile_parser_handles_kimi_eval_direction():
    parsed = RoleProfileService.parse_keyword("kimi的大模型Eval评测方向")

    assert parsed.companies == ["月之暗面"]
    assert "大模型 Eval 评测" in parsed.directions
    assert "kimi" in parsed.normalizedTerms


@pytest.mark.asyncio
async def test_role_profile_api_builds_evidence_profile_and_filters_low_value(client):
    runtime_result = {
        "sessionId": "session-role-1",
        "status": "partial_success",
        "items": [
            {
                "source": "official_job",
                "source_url": "https://jobs.bytedance.com/experienced/position/1/detail",
                "title": "AI 测试开发工程师",
                "snippet": "岗位职责：负责 AI 产品自动化测试平台建设。任职要求：Python、接口测试、质量保障。",
                "published_at": "2026-05-01",
                "has_full_text": False,
            },
            {
                "source": "nowcoder",
                "source_url": "https://www.nowcoder.com/discuss/1",
                "title": "阿里 自动化测试 面经",
                "snippet": "一面问了测试平台设计、Java、接口自动化怎么做，还追问数据库。",
                "published_at": datetime.utcnow().isoformat(),
                "has_full_text": False,
            },
            {
                "source": "nowcoder",
                "source_url": "https://www.nowcoder.com/discuss/low",
                "title": "阿里 自动化测试 内推",
                "snippet": "急招 hc 多，欢迎投递。",
                "published_at": datetime.utcnow().isoformat(),
                "has_full_text": False,
            },
        ],
        "total": 3,
        "sourcesStatus": {"official_job": {"status": "ok"}, "nowcoder": {"status": "ok"}},
        "searchDuration": 123,
        "qualityReport": {"fetchedCount": 0},
    }

    with (
        patch("app.api.routes_role_profile.get_registered_adapters", return_value={}),
        patch("app.services.role_profile_service.AgentRuntime.run_search", new=AsyncMock(return_value=runtime_result)),
        patch("app.services.role_profile_service.RoleProfileService._llm_available", return_value=False),
    ):
        response = await client.post(
            "/api/role-profile/search",
            json={"keyword": "阿里+字节的自动化测试工程师"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["sessionId"] == "session-role-1"
    assert data["parsedQuery"]["companies"] == ["阿里巴巴", "字节跳动"]
    assert data["profile"]["evidenceStats"]["jobPostingCount"] == 1
    assert data["profile"]["evidenceStats"]["interviewEvidenceCount"] == 1
    assert data["qualityReport"]["roleEvidenceCount"] == 2
    evidence_urls = [ev["sourceUrl"] for ev in data["profile"]["evidence"]]
    assert "https://www.nowcoder.com/discuss/low" not in evidence_urls
    assert any(skill["skill"] == "测试平台与自动化框架" for skill in data["profile"]["skillWeights"])
    assert data["profile"]["preparationPlan"]


@pytest.mark.asyncio
async def test_role_profile_uses_local_job_radar_cache_for_alibaba_bytedance(client, tmp_path, monkeypatch):
    cache_dir = tmp_path / "ai-job-radar"
    data_dir = cache_dir / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "jobs.json").write_text(json.dumps([
        {
            "platform": "quark",
            "company": "阿里巴巴",
            "title": "千问事业部-高级测试开发工程师-杭州",
            "department": "千问事业部",
            "location": "杭州",
            "description": "负责大模型产品测试平台建设、接口自动化、质量保障和问题定位。",
            "requirements": "熟悉 Python/Java，理解 CI/CD、自动化测试框架和服务端质量治理。",
            "url": "https://talent.quark.cn/off-campus/position-detail?positionId=100012140008",
            "publish_date": "2026年04月18日",
        },
        {
            "platform": "bytedance",
            "company": "字节跳动",
            "title": "AI 自动化测试开发工程师",
            "department": "Seed",
            "location": "北京",
            "description": "负责 AI 助手业务的自动化测试、接口测试、稳定性建设和线上质量分析。",
            "requirements": "熟悉测试开发、平台工具建设、数据库和服务端排查。",
            "url": "https://jobs.bytedance.com/experienced/position/1/detail",
            "publish_date": "2026-05-01",
        },
        {
            "platform": "quark",
            "company": "阿里巴巴",
            "title": "千问事业部-AIGC 产品经理",
            "description": "负责产品规划。",
            "url": "https://talent.quark.cn/off-campus/position-detail?positionId=product",
        },
    ], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(role_profile_module.settings, "job_radar_cache_dir", str(cache_dir))
    monkeypatch.setattr(role_profile_module.settings, "job_radar_cache_auto_detect", False)

    runtime_result = {
        "sessionId": "session-local-jd",
        "status": "partial_success",
        "items": [
            {
                "source": "nowcoder",
                "source_url": "https://www.nowcoder.com/discuss/automation",
                "title": "阿里 自动化测试 面经",
                "snippet": "一面问了测试平台设计、接口自动化怎么做，还追问数据库。",
                "published_at": datetime.utcnow().isoformat(),
                "has_full_text": False,
            }
        ],
        "sourcesStatus": {"official_job": {"status": "config_error"}},
        "searchDuration": 21,
        "qualityReport": {},
    }

    with (
        patch("app.api.routes_role_profile.get_registered_adapters", return_value={}),
        patch("app.services.role_profile_service.AgentRuntime.run_search", new=AsyncMock(return_value=runtime_result)),
        patch("app.services.role_profile_service.RoleProfileService._llm_available", return_value=False),
    ):
        response = await client.post(
            "/api/role-profile/search",
            json={"keyword": "阿里+字节的自动化测试工程师"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["profile"]["evidenceStats"]["jobPostingCount"] == 2
    assert data["profile"]["evidenceStats"]["liveJobPostingCount"] == 0
    assert data["profile"]["evidenceStats"]["localJobRadarEvidenceCount"] == 2
    assert data["qualityReport"]["localJobRadarEvidenceCount"] == 2
    assert data["sourcesStatus"]["local_job_radar_cache"]["status"] == "ok"
    local_evidence = [ev for ev in data["profile"]["evidence"] if ev["source"] == "local_job_radar_cache"]
    assert len(local_evidence) == 2
    assert all("local_snapshot" in ev["limitations"] for ev in local_evidence)
    assert any("阿里巴巴" in (ev["quote"] or "") for ev in local_evidence)
    assert any("字节跳动" in (ev["quote"] or "") for ev in local_evidence)
    assert "product" not in {ev["sourceUrl"] for ev in local_evidence}


@pytest.mark.asyncio
async def test_role_profile_uses_local_job_radar_cache_for_kimi_eval(client, tmp_path, monkeypatch):
    cache_dir = tmp_path / "ai-job-radar"
    data_dir = cache_dir / "data"
    data_dir.mkdir(parents=True)
    (data_dir / "jobs.json").write_text(json.dumps([
        {
            "platform": "moonshot",
            "company": "月之暗面",
            "title": "Eval Engineer - Moonshot AI",
            "department": "Kimi",
            "location": "北京",
            "description": "负责 Kimi 大模型评测体系、Benchmark 构建、badcase 归因和 Agent 任务成功率分析。",
            "requirements": "熟悉 LLM Eval、数据集设计、人工评估一致性和模型效果分析。",
            "url": "https://jobs.ashbyhq.com/moonshot-ai/abc",
            "publish_date": "2026-05-20",
        }
    ], ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(role_profile_module.settings, "job_radar_cache_dir", str(cache_dir))
    monkeypatch.setattr(role_profile_module.settings, "job_radar_cache_auto_detect", False)

    runtime_result = {
        "sessionId": "session-kimi-local-jd",
        "status": "partial_success",
        "items": [],
        "sourcesStatus": {"official_job": {"status": "config_error"}},
        "searchDuration": 18,
        "qualityReport": {},
    }

    with (
        patch("app.api.routes_role_profile.get_registered_adapters", return_value={}),
        patch("app.services.role_profile_service.AgentRuntime.run_search", new=AsyncMock(return_value=runtime_result)),
        patch("app.services.role_profile_service.RoleProfileService._llm_available", return_value=False),
    ):
        response = await client.post(
            "/api/role-profile/search",
            json={"keyword": "kimi的大模型Eval评测方向"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["parsedQuery"]["companies"] == ["月之暗面"]
    assert data["profile"]["evidenceStats"]["jobPostingCount"] == 1
    assert data["qualityReport"]["localJobRadarEvidenceCount"] == 1
    assert data["profile"]["evidence"][0]["source"] == "local_job_radar_cache"
    assert "not_live_verified" in data["profile"]["evidence"][0]["limitations"]
    assert any(skill["skill"] == "大模型/Agent 评测方法" for skill in data["profile"]["skillWeights"])


@pytest.mark.asyncio
async def test_role_profile_llm_timeout_falls_back_to_heuristic(db_session, monkeypatch):
    service = RoleProfileService(db=db_session, adapters={})
    parsed = RoleProfileService.parse_keyword("kimi的大模型Eval评测方向")
    evidence = [
        RoleProfileEvidence(
            evidenceType="interview_evidence",
            source="nowcoder",
            sourceUrl="https://www.nowcoder.com/discuss/1",
            title="Kimi 大模型 Eval 面经",
            quote="一面问了如何设计 benchmark、如何做 badcase 归因。",
            confidence=0.82,
        )
    ]

    async def _slow_chat_json(*args, **kwargs):
        await asyncio.sleep(1)
        return {"roleSummary": "should not be used"}

    monkeypatch.setattr("app.services.role_profile_service.settings.role_profile_llm_timeout", 0.01)
    with (
        patch("app.services.role_profile_service.RoleProfileService._llm_available", return_value=True),
        patch("app.llm.client.llm_client.chat_json", new=AsyncMock(side_effect=_slow_chat_json)),
    ):
        profile = await service._build_profile(parsed, evidence)

    assert "should not be used" not in profile.roleSummary
    assert profile.confidence in {"low", "medium"}
    assert profile.preparationPlan
