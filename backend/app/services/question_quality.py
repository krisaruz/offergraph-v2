"""Quality gates for interview questions shown in the Feed."""

from __future__ import annotations

import re
from typing import Any

GENERIC_PATTERNS = [
    r"薪资",
    r"期望薪资",
    r"项目经历(相关)?(问题)?",
    r"项目经验(相关)?(问题)?",
    r"项目(相关)?问题$",
    r"技术(相关)?问题$",
    r"基础(相关)?问题$",
    r"八股(文)?(相关)?(问题)?$",
    r"算法题?$",
    r"数据库(相关)?问题$",
    r"Java(相关)?问题$",
    r".*相关技术问题$",
    r".*相关(的)?一些技术问题$",
    r"问(了)?(.*)?项目$",
    r"问(了)?(.*)?基础$",
    r"自我介绍",
    r"(介绍|讲一下|说一下)(你)?(自己)?的?项目$",
]

QUESTION_CUES = [
    "怎么",
    "如何",
    "为什么",
    "什么",
    "区别",
    "原理",
    "流程",
    "实现",
    "设计",
    "优化",
    "排查",
    "保证",
    "解决",
    "处理",
    "介绍",
    "讲一下",
    "说一下",
    "解释",
    "手撕",
    "写一个",
    "实现一个",
]

TECH_TERMS = [
    "redis",
    "mysql",
    "sql",
    "jvm",
    "gc",
    "spring",
    "springboot",
    "http",
    "https",
    "tcp",
    "udp",
    "线程",
    "线程池",
    "进程",
    "锁",
    "并发",
    "索引",
    "事务",
    "缓存",
    "一致性",
    "消息队列",
    "mq",
    "kafka",
    "rocketmq",
    "分布式",
    "限流",
    "熔断",
    "降级",
    "微服务",
    "高并发",
    "秒杀",
    "库存",
    "数据库",
    "算法",
    "链表",
    "数组",
    "二叉树",
    "红黑树",
    "堆",
    "栈",
    "队列",
    "图",
    "动态规划",
    "dp",
    "排序",
    "复杂度",
    "linux",
    "操作系统",
    "网络",
    "rpc",
    "dubbo",
    "nginx",
    "elasticsearch",
    "es",
    "大模型",
    "机器学习",
]


def _normalize(text: str | None) -> str:
    return re.sub(r"\s+", "", text or "").strip("：:，,。.；;？?！!")


def is_specific_interview_question(text: str | None, category: str | None = None) -> bool:
    """Return whether the text is a concrete, answerable interview question."""
    normalized = _normalize(text)
    if not normalized:
        return False

    lower = normalized.lower()
    if any(re.fullmatch(pattern, normalized, flags=re.IGNORECASE) for pattern in GENERIC_PATTERNS):
        return False
    if any(re.search(pattern, normalized, flags=re.IGNORECASE) for pattern in GENERIC_PATTERNS[:4]):
        return False

    has_question_cue = any(cue in normalized for cue in QUESTION_CUES)
    has_tech_term = any(term in lower for term in TECH_TERMS)
    has_concrete_length = len(normalized) >= 8
    is_technical_category = category in {
        "fundamentals",
        "algorithm",
        "system_design",
        "ai",
        "project",
    }

    if has_question_cue and has_concrete_length:
        return True
    if is_technical_category and has_tech_term and has_concrete_length:
        return True
    return False


def question_specificity_score(question: Any, evidence_quote: str | None = None) -> tuple[int, int, int]:
    """Sort key: higher means better Feed representative question."""
    text = getattr(question, "question_text", None)
    category = getattr(question, "category", None)
    normalized = _normalize(text)
    lower = normalized.lower()

    has_evidence = 1 if evidence_quote else 0
    has_question_cue = 1 if any(cue in normalized for cue in QUESTION_CUES) else 0
    tech_hits = sum(1 for term in TECH_TERMS if term in lower)
    category_bonus = 1 if category in {"algorithm", "system_design", "fundamentals", "ai"} else 0
    return (has_evidence, has_question_cue + category_bonus, tech_hits)
