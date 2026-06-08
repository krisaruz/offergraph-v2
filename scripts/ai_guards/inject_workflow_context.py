#!/usr/bin/env python3
"""
Claude Code UserPromptSubmit Hook：根据用户 prompt 自动注入流程上下文。

从 stdin 读取 Claude Code hook payload（JSON），分析用户 prompt 内容，
判断任务类型，输出 additionalContext 提醒 Claude 遵循对应流程。

兼容 Windows。
"""

import json
import sys
import os


TASK_KEYWORDS = {
    "requirement": [
        "新增", "实现", "改", "调整", "优化", "重构", "需求", "功能",
        "页面", "接口", "数据模型", "PRD", "流程", "设计",
        "新功能", "变更", "增加", "添加", "修改", "更新",
    ],
    "frontend": [
        "前端", "页面", "组件", "UI", "UX", "React", "Vue", "CSS",
        "样式", "表单", "按钮", "frontend", "component", "layout",
        "Next.js", "Tailwind", "布局", "导航", "路由", "菜单",
    ],
    "visual": [
        "丑", "好看", "设计", "视觉", "布局", "审美", "dashboard",
        "landing", "style", "design", "美化", "重新设计", "redesign",
        "配色", "颜色", "主题", "dark mode", "暗色",
    ],
    "backend": [
        "接口", "API", "后端", "FastAPI", "数据库", "schema", "model",
        "runtime", "adapter", "LLM", "prompt", "服务",
        "SQLAlchemy", "Pydantic", "Redis", "缓存",
    ],
    "bugfix": [
        "bug", "报错", "错误", "异常", "修复", "不工作", "broken",
        "fix", "error", "failed", "崩溃", "白屏", "undefined",
        "TypeError", "无法", "不能",
    ],
    "test": [
        "测试", "test", "pytest", "coverage", "回归", "单元测试",
        "集成测试", "端到端", "e2e", "mock",
    ],
}

CONTEXT_MESSAGES = {
    "requirement": (
        "检测到需求或需求变更：必须先执行强制需求处理流程。"
        "默认顺序为：理解上下文 -> 主动澄清 -> 复述需求 -> "
        "更新 PRD.md -> 获取开发许可 -> 实现与验证 -> 交付说明。"
        "不得直接进入编码。所有流程图必须使用 Mermaid。"
        "所有需求变更必须先更新 PRD.md 或对应设计文档。"
    ),
    "frontend": (
        "检测到前端相关任务。请参考以下流程：\n"
        "1. 阅读 AGENTS.md 第 4-5 节（前端功能规则、前端视觉设计规则）\n"
        "2. 使用 frontend-safe-implementation skill 确保状态完整性\n"
        "3. 覆盖 loading / empty / error / success / failed request 状态\n"
        "4. 完成后运行 typecheck、lint、build\n"
        "5. 使用 test-regression-review skill 完成二次审查"
    ),
    "visual": (
        "检测到前端/视觉相关任务：必须先使用 frontend-design、"
        "offergraph-visual-style、frontend-safe-implementation。"
        "实现前先确定视觉方向、信息层级、组件结构、色彩和排版策略。"
        "禁止默认 AI SaaS 风格。"
        "实现后必须使用 visual-reviewer 审查视觉质量，发现 must-fix 必须修复。"
    ),
    "backend": (
        "检测到后端/API 相关任务。请参考以下流程：\n"
        "1. 阅读 AGENTS.md 第 2-3 节（PRD 同步、编码规则）\n"
        "2. 检查 schema、路由、服务边界是否需要调整\n"
        "3. 遵守架构调用链：Route -> Service -> AgentRuntime -> ...\n"
        "4. 涉及数据模型变更时先备份 offergraph.db\n"
        "5. 完成后运行 cd backend && pytest tests/ -v"
    ),
    "bugfix": (
        "检测到 Bug 修复任务。请注意：\n"
        "1. 禁止猜测性修复。先通过日志、测试、最小复现验证根因\n"
        "2. 修复前先写失败测试复现 Bug\n"
        "3. 修复后确保测试通过\n"
        "4. 检查是否有其他地方存在同类问题"
    ),
    "test": (
        "检测到测试相关任务。请注意：\n"
        "1. 测试必须断言实际行为，不允许只验证'不会报错'\n"
        "2. 不允许只检查 metadata、状态码或数组长度\n"
        "3. 必须覆盖正向 + 边界 + 异常路径\n"
        "4. 禁止空测试"
    ),
}


def detect_task_types(prompt: str) -> list[str]:
    """根据 prompt 内容检测任务类型。"""
    prompt_lower = prompt.lower()
    detected = []
    for task_type, keywords in TASK_KEYWORDS.items():
        for keyword in keywords:
            if keyword.lower() in prompt_lower:
                detected.append(task_type)
                break
    return detected


def has_shadcn_skills() -> bool:
    """检查项目是否安装了 shadcn 相关 skills。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(script_dir, "..", ".."))
    shadcn_discovery = os.path.join(
        project_root, ".claude", "skills", "shadcn-component-discovery"
    )
    return os.path.isdir(shadcn_discovery)


def build_context(task_types: list[str]) -> str:
    """根据检测到的任务类型构建上下文。"""
    if not task_types:
        return (
            "提醒：请先阅读 AGENTS.md 了解项目开发规范。"
            "完成后使用 test-regression-review skill 进行二次审查。"
        )

    parts = []

    if "requirement" in task_types:
        parts.append(CONTEXT_MESSAGES["requirement"])

    for task_type in task_types:
        if task_type != "requirement" and task_type in CONTEXT_MESSAGES:
            parts.append(CONTEXT_MESSAGES[task_type])

    if ("frontend" in task_types or "visual" in task_types) and has_shadcn_skills():
        parts.append(
            "当前项目存在 Tailwind/shadcn 相关能力："
            "优先复用成熟组件和 blocks，不要从零乱造 UI。"
        )

    parts.append(
        "\n通用提醒：完成后确保最终回复包含改动摘要、PRD 同步、影响范围、"
        "测试与验证、二次审查结果、未验证部分、回退方案。"
    )

    return "\n\n---\n\n".join(parts)


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    prompt = payload.get("prompt", "")
    if not prompt:
        sys.exit(0)

    task_types = detect_task_types(prompt)
    context = build_context(task_types)

    output = {"additionalContext": context}
    json.dump(output, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
