"""Tests for Ranker trust scoring and final ranking."""

from datetime import datetime, timedelta

import pytest

from app.runtime.ranker import SOURCE_RELIABILITY, Ranker, TrustScore


@pytest.fixture
def ranker() -> Ranker:
    return Ranker()


def _make_item(
    *,
    source: str = "nowcoder",
    source_url: str = "https://nowcoder.com/discuss/1",
    title: str = "字节跳动 后端 一面面经",
    snippet: str = "面试官问了算法题和项目经历",
    published_at: str | None = None,
    evidence_coverage: float = 0.0,
    extraction_confidence: float = 0.0,
) -> dict:
    if published_at is None:
        published_at = datetime.utcnow().isoformat()
    return {
        "source": source,
        "source_url": source_url,
        "title": title,
        "snippet": snippet,
        "published_at": published_at,
        "evidence_coverage": evidence_coverage,
        "extraction_confidence": extraction_confidence,
    }


def test_rank_empty_results(ranker):
    assert ranker.rank([], {}) == []


def test_rank_adds_trust_and_final_score_fields(ranker):
    items = [_make_item()]
    ranked = ranker.rank(items, {})

    assert len(ranked) == 1
    assert "trust_score" in ranked[0]
    assert "final_score" in ranked[0]
    assert "trust_label" in ranked[0]
    assert ranked[0]["final_score"] > 0


def test_rank_sorts_by_final_score_descending(ranker):
    high = _make_item(
        source="nowcoder",
        source_url="https://nowcoder.com/high",
        title="阿里巴巴 后端开发 一面二面三面全流程面经",
        snippet="详细记录了每轮面试题和答案，算法题手撕",
        evidence_coverage=0.9,
        extraction_confidence=0.9,
    )
    low = _make_item(
        source="xiaohongshu",
        source_url="https://xiaohongshu.com/low",
        title="随便聊聊",
        snippet="短内容",
        published_at=(datetime.utcnow() - timedelta(days=90)).isoformat(),
        evidence_coverage=0.0,
        extraction_confidence=0.0,
    )

    ranked = ranker.rank([low, high], {})

    assert len(ranked) == 2, f"应返回2条结果，实际: {len(ranked)}"
    assert ranked[0]["source_url"] == "https://nowcoder.com/high"
    assert ranked[1]["source_url"] == "https://xiaohongshu.com/low"


def test_compute_trust_score_source_reliability_mapping(ranker):
    nowcoder_item = _make_item(source="nowcoder")
    xhs_item = _make_item(source="xiaohongshu", source_url="https://xhs.com/1")

    nowcoder_trust = ranker._compute_trust_score(nowcoder_item, {})
    xhs_trust = ranker._compute_trust_score(xhs_item, {})

    assert nowcoder_trust.source_reliability == SOURCE_RELIABILITY["nowcoder"]
    assert xhs_trust.source_reliability == SOURCE_RELIABILITY["xiaohongshu"]
    assert nowcoder_trust.source_reliability > xhs_trust.source_reliability


def test_compute_trust_score_domain_boost_from_url(ranker):
    item = _make_item(
        source="search_engine",
        source_url="https://www.zhihu.com/question/123",
    )

    trust = ranker._compute_trust_score(item, {})

    assert trust.source_reliability >= SOURCE_RELIABILITY["zhihu.com"]


def test_compute_freshness_recent_content(ranker):
    recent = datetime.utcnow() - timedelta(days=2)
    score = ranker._compute_freshness(recent.isoformat())
    assert score == 1.0


def test_compute_freshness_age_buckets(ranker):
    """实现：<=180d=1.0, <=365d=0.5, <=730d=0.2, >730d=0.05"""
    within_180 = datetime.utcnow() - timedelta(days=120)
    between_180_365 = datetime.utcnow() - timedelta(days=250)
    between_365_730 = datetime.utcnow() - timedelta(days=500)
    beyond_730 = datetime.utcnow() - timedelta(days=800)

    assert ranker._compute_freshness(within_180.isoformat()) == 1.0
    assert ranker._compute_freshness(between_180_365.isoformat()) == 0.5
    assert ranker._compute_freshness(between_365_730.isoformat()) == 0.2
    assert ranker._compute_freshness(beyond_730.isoformat()) == 0.05


def test_compute_freshness_missing_or_invalid(ranker):
    assert ranker._compute_freshness(None) == 0.3
    assert ranker._compute_freshness("not-a-date") == 0.3


def test_compute_freshness_from_text_context(ranker):
    """从标题文本中提取日期信息"""
    score = ranker._compute_freshness(None, text_context="2025年6月面试")
    assert score >= 0.5

    old_score = ranker._compute_freshness(None, text_context="2020年的面试经历")
    assert old_score <= 0.2


def test_content_richness_keywords(ranker):
    """包含面试轮次和题目关键词的标题得分更高"""
    rich = ranker._compute_content_richness(
        "阿里巴巴后端一面二面面经 算法题手撕详细记录",
        "面试官问了很多项目经验，八股文和场景题"
    )
    poor = ranker._compute_content_richness(
        "水",
        ""
    )
    assert rich > poor
    assert rich >= 0.5


def test_duplicate_support_increases_with_url_counts(ranker):
    item = _make_item(source_url="https://example.com/dup")
    low_support = ranker._compute_trust_score(item, {"https://example.com/dup": 1})
    high_support = ranker._compute_trust_score(item, {"https://example.com/dup": 6})

    assert high_support.duplicate_support > low_support.duplicate_support
    assert high_support.duplicate_support == 1.0


def test_trust_label_for_high_quality_item(ranker):
    item = _make_item(
        source="nowcoder",
        title="腾讯后端一面二面三面全流程面经 详细",
        snippet="面试题和算法手撕全记录，八股文总结",
        evidence_coverage=0.9,
        extraction_confidence=0.9,
        published_at=(datetime.utcnow() - timedelta(days=2)).isoformat(),
    )
    trust = ranker._compute_trust_score(item, {item["source_url"]: 3})
    label = ranker._trust_label(trust)

    assert "真实来源" in label
    assert "证据充分" in label
    assert "近期内容" in label
    assert "多篇支持" in label


def test_trust_label_defaults_to_pending_verification(ranker):
    item = _make_item(
        source="unknown_source",
        source_url="https://unknown.test/1",
        title="短标题",
        snippet="",
        published_at=(datetime.utcnow() - timedelta(days=400)).isoformat(),
    )
    trust = ranker._compute_trust_score(item, {})
    label = ranker._trust_label(trust)

    assert label == "待验证"


def test_recent_detailed_content_ranks_above_old_sparse(ranker):
    """最近+详细的内容必须排在旧+简陋的内容之上"""
    new_detailed = _make_item(
        source="xiaohongshu",
        source_url="https://xhs.com/new",
        title="2025 阿里巴巴后端一面二面面经 已offer",
        snippet="详细分享面试题目和答案，算法手撕",
        published_at=(datetime.utcnow() - timedelta(days=5)).isoformat(),
    )
    old_sparse = _make_item(
        source="nowcoder",
        source_url="https://nowcoder.com/old",
        title="阿里面试",
        snippet="很简短",
        published_at=(datetime.utcnow() - timedelta(days=400)).isoformat(),
    )

    ranked = ranker.rank([old_sparse, new_detailed], {})
    assert ranked[0]["source_url"] == "https://xhs.com/new"


def test_relevance_social_recruit_ranks_above_intern(ranker):
    """社招画像下：社招面经必须排在实习面经之上"""
    profile = {
        "identity": "working_switch",
        "target_companies": ["阿里巴巴"],
        "directions": ["后端开发"],
    }
    social = _make_item(
        source="nowcoder",
        source_url="https://nowcoder.com/social",
        title="阿里巴巴 后端开发 社招面经 三面全流程",
        snippet="系统设计、八股文、手撕算法，详细记录",
        published_at=(datetime.utcnow() - timedelta(days=10)).isoformat(),
    )
    intern = _make_item(
        source="nowcoder",
        source_url="https://nowcoder.com/intern",
        title="阿里巴巴 后端开发 暑期实习面经",
        snippet="实习一面面试题分享，算法",
        published_at=(datetime.utcnow() - timedelta(days=5)).isoformat(),
    )

    ranked = ranker.rank([intern, social], {}, profile=profile)
    assert ranked[0]["source_url"] == "https://nowcoder.com/social", \
        f"社招面经应排第一，实际: {ranked[0]['title']}"


def test_relevance_matching_company_ranks_above_other(ranker):
    """匹配目标公司的面经应排在非目标公司之上"""
    profile = {
        "identity": "working_switch",
        "target_companies": ["阿里巴巴"],
        "directions": ["后端开发"],
    }
    target = _make_item(
        source="nowcoder",
        source_url="https://nowcoder.com/ali",
        title="阿里巴巴 后端社招 面经",
        snippet="阿里后端社招面试",
    )
    other = _make_item(
        source="nowcoder",
        source_url="https://nowcoder.com/other",
        title="某小厂 后端社招 面经",
        snippet="某小厂后端社招面试",
    )

    ranked = ranker.rank([other, target], {}, profile=profile)
    assert ranked[0]["source_url"] == "https://nowcoder.com/ali", \
        f"目标公司面经应排第一，实际: {ranked[0]['title']}"


def test_relevance_negative_label_penalty(ranker):
    """搜社招时，实习/校招内容应被降权"""
    profile = {
        "identity": "working_switch",
        "target_companies": [],
        "directions": ["后端开发"],
    }
    social = _make_item(
        source="nowcoder",
        source_url="https://nowcoder.com/s",
        title="后端开发 社招面经",
        snippet="社招面试分享",
    )
    intern = _make_item(
        source="nowcoder",
        source_url="https://nowcoder.com/i",
        title="后端开发 实习面经",
        snippet="实习面试分享",
    )

    ranked = ranker.rank([intern, social], {}, profile=profile)
    social_score = next(r for r in ranked if r["source_url"] == "https://nowcoder.com/s")["final_score"]
    intern_score = next(r for r in ranked if r["source_url"] == "https://nowcoder.com/i")["final_score"]
    assert social_score > intern_score, \
        f"社招应高于实习: 社招={social_score:.3f}, 实习={intern_score:.3f}"
