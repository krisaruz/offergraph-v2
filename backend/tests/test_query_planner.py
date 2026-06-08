"""Tests for QueryPlanner search plan generation."""

import json

import pytest

from app.runtime.query_planner import QueryPlanner


@pytest.fixture
def planner() -> QueryPlanner:
    return QueryPlanner()


def test_plan_working_switch_generates_social_recruitment_queries(planner):
    profile = {
        "identity": "working_switch",
        "target_companies": ["字节跳动"],
        "directions": ["后端开发"],
        "regions": ["北京"],
        "custom_needs": "",
    }

    plan = planner.plan(profile)

    assert len(plan.queries) >= 2
    assert plan.max_results_per_query == 10
    assert plan.max_fetch_urls == 10

    queries_text = [q.query for q in plan.queries]
    # 精确查询必须包含身份标签"社招"
    assert any("字节跳动" in q and "后端开发" in q and "社招" in q for q in queries_text), \
        f"搜索词中必须包含'社招'，实际生成: {queries_text}"
    # 公司+方向+面试
    assert any("字节跳动" in q and "后端开发" in q and "面试" in q for q in queries_text)

    # metadata 字段也正确
    assert all(q.candidate_type == "社招" for q in plan.queries)


def test_plan_fresh_grad_generates_campus_recruitment_queries(planner):
    profile = {
        "identity": "student_autumn",
        "target_companies": ["腾讯"],
        "directions": ["算法"],
        "regions": [],
        "custom_needs": "",
    }

    plan = planner.plan(profile)
    queries_text = [q.query for q in plan.queries]

    # 搜索词必须包含"校招"
    assert any("腾讯" in q and "算法" in q and "校招" in q for q in queries_text), \
        f"搜索词中必须包含'校招'，实际生成: {queries_text}"
    assert any("腾讯" in q and "算法" in q and "面试" in q for q in queries_text)
    assert all(q.candidate_type == "校招" for q in plan.queries)


def test_plan_intern_generates_internship_queries(planner):
    profile = {
        "identity": "student_summer_intern",
        "target_companies": ["美团"],
        "directions": ["前端"],
        "regions": ["上海"],
        "custom_needs": "",
    }

    plan = planner.plan(profile)
    queries_text = [q.query for q in plan.queries]

    # 搜索词必须包含"实习"
    assert any("美团" in q and "前端" in q and "实习" in q for q in queries_text), \
        f"搜索词中必须包含'实习'，实际生成: {queries_text}"
    assert any("美团" in q and "前端" in q and "面试" in q for q in queries_text)
    assert all(q.candidate_type == "实习" for q in plan.queries)


def test_plan_most_precise_query_first(planner):
    """第一条查询应该是最精确的（公司+方向+身份+面经），保证相关性"""
    profile = {
        "identity": "working_switch",
        "target_companies": ["阿里"],
        "directions": ["Java"],
        "regions": [],
        "custom_needs": "系统设计",
    }

    plan = planner.plan(profile)

    assert plan.queries[0].query == "阿里 Java 社招 面经 2025"
    assert plan.queries[0].priority == 0


def test_plan_includes_cross_company_direction_query(planner):
    """应包含跨公司的方向+身份查询，扩大覆盖面"""
    profile = {
        "identity": "working_switch",
        "target_companies": ["字节跳动"],
        "directions": ["后端开发"],
        "regions": [],
        "custom_needs": "",
    }

    plan = planner.plan(profile)
    queries_text = [q.query for q in plan.queries]

    # 跨公司搜索：方向+身份+面经
    assert any("后端开发" in q and "社招" in q and "面经" in q and "字节跳动" not in q for q in queries_text), \
        f"跨公司查询必须包含'社招'，实际生成: {queries_text}"


def test_plan_empty_companies_generates_open_queries(planner):
    profile = {
        "identity": "working_switch",
        "target_companies": [],
        "directions": ["后端"],
        "regions": [],
    }

    plan = planner.plan(profile)

    assert len(plan.queries) > 0
    queries_text = [q.query for q in plan.queries]
    assert any("后端" in q and "面经" in q for q in queries_text)
    assert all(q.company is None for q in plan.queries)


def test_plan_empty_directions_generates_open_queries(planner):
    profile = {
        "identity": "working_switch",
        "target_companies": ["百度"],
        "directions": [],
        "regions": [],
    }

    plan = planner.plan(profile)

    assert len(plan.queries) > 0
    queries_text = [q.query for q in plan.queries]
    assert any("百度" in q and "面试" in q for q in queries_text)


def test_plan_truncates_companies_and_directions(planner):
    companies = [f"公司{i}" for i in range(10)]
    directions = [f"方向{i}" for i in range(10)]

    profile = {
        "identity": "working_switch",
        "target_companies": companies,
        "directions": directions,
        "regions": [],
    }

    plan = planner.plan(profile)

    assert len(plan.queries) <= QueryPlanner.MAX_QUERIES
    used_companies = {q.company for q in plan.queries if q.company}
    assert len(used_companies) <= QueryPlanner.MAX_COMPANIES


def test_plan_parses_json_string_fields(planner):
    profile = {
        "identity": "working_switch",
        "target_companies": json.dumps(["华为"]),
        "directions": json.dumps(["嵌入式"]),
        "regions": json.dumps(["深圳"]),
        "custom_needs": "",
    }

    plan = planner.plan(profile)

    assert len(plan.queries) > 0
    # 应包含公司+方向的面经查询
    assert any("华为" in q.query and "面经" in q.query for q in plan.queries)
