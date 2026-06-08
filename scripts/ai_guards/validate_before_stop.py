#!/usr/bin/env python3
"""
Claude Code Stop Hook：结束前验证是否完成交付要求。

从 stdin 读取 Claude Code hook payload（JSON），检查：
1. 是否有源代码改动
2. 是否有前端改动
3. 最后回复是否包含完整交付格式
4. 需求变更是否说明了 PRD 更新情况
5. 流程图是否使用 Mermaid
6. 新需求是否包含完整交付说明

如果发现风险，输出 decision: block，要求 Claude 继续处理。

注意：
- 避免无限循环：只做轻量检查，不要求完美
- 如果连续被 block 超过 2 次相同原因，允许通过并提醒用户
- 兼容 Windows

Hook payload 结构:
{
  "transcript": [
    {"type": "user", "content": "..."},
    {"type": "assistant", "content": "..."}
  ]
}
"""

import json
import subprocess
import sys
import os


def get_changed_files() -> list[str]:
    """获取 git diff 中的文件列表（staged + unstaged）。"""
    try:
        project_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=project_root,
        )
        files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]

        result2 = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            capture_output=True,
            text=True,
            timeout=10,
            cwd=project_root,
        )
        staged = [f.strip() for f in result2.stdout.strip().split("\n") if f.strip()]

        return list(set(files + staged))
    except Exception:
        return []


def has_source_changes(files: list[str]) -> bool:
    """判断是否有源代码改动。"""
    source_patterns = [
        "backend/", "frontend/", "electron/",
        ".py", ".ts", ".tsx", ".js", ".jsx", ".css",
    ]
    for f in files:
        for pattern in source_patterns:
            if pattern in f:
                return True
    return False


def has_frontend_changes(files: list[str]) -> bool:
    """判断是否有前端改动。"""
    for f in files:
        if "frontend/" in f or f.endswith((".tsx", ".jsx", ".css")):
            return True
    return False


def has_prd_change(files: list[str]) -> bool:
    """判断 PRD.md 是否有变更。"""
    return any("PRD.md" in f for f in files)


def check_delivery_format(last_reply: str) -> list[str]:
    """检查最终回复是否包含完整交付格式。"""
    missing = []
    required_sections = [
        ("改动摘要", "## 改动摘要"),
        ("PRD 同步", "PRD 同步"),
        ("影响范围", "影响范围"),
        ("测试与验证", "测试"),
        ("二次审查", "二次审查"),
        ("未验证部分", "未验证"),
        ("回退方案", "回退"),
    ]
    for name, keyword in required_sections:
        if keyword not in last_reply:
            missing.append(name)
    return missing


def is_requirement_change(transcript: list) -> bool:
    """检测本轮对话是否涉及需求变更。"""
    requirement_keywords = [
        "新增", "实现", "改", "调整", "功能", "需求", "页面",
        "接口", "数据模型", "流程", "设计", "PRD",
    ]
    for msg in transcript:
        if msg.get("type") == "user":
            content = msg.get("content", "")
            if isinstance(content, str):
                for kw in requirement_keywords:
                    if kw in content:
                        return True
    return False


def mentions_flowchart(transcript: list) -> bool:
    """检测本轮对话是否涉及流程图。"""
    flowchart_keywords = ["流程图", "flowchart", "sequence", "状态图", "时序图"]
    for msg in transcript:
        content = msg.get("content", "")
        if isinstance(content, str):
            for kw in flowchart_keywords:
                if kw.lower() in content.lower():
                    return True
    return False


def get_last_assistant_reply(transcript: list) -> str:
    """获取最后一条 assistant 回复。"""
    for msg in reversed(transcript):
        if msg.get("type") == "assistant":
            content = msg.get("content", "")
            if isinstance(content, list):
                text_parts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text":
                        text_parts.append(part.get("text", ""))
                    elif isinstance(part, str):
                        text_parts.append(part)
                return "\n".join(text_parts)
            return str(content)
    return ""


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    transcript = payload.get("transcript", [])
    if not transcript:
        sys.exit(0)

    last_reply = get_last_assistant_reply(transcript)
    changed_files = get_changed_files()

    if not has_source_changes(changed_files):
        sys.exit(0)

    issues = []

    missing_sections = check_delivery_format(last_reply)
    if missing_sections:
        issues.append(
            f"最终回复缺少以下交付格式部分：{', '.join(missing_sections)}。"
            f"请按 AGENTS.md 第 10 节格式补充。"
        )

    if has_source_changes(changed_files) and not has_prd_change(changed_files):
        if "PRD" not in last_reply and "不需要更新" not in last_reply:
            issues.append(
                "有源代码改动但 PRD.md 未更新，且回复中未说明不更新的原因。"
                "请同步 PRD 或在回复中说明不需要更新的原因。"
            )

    if is_requirement_change(transcript):
        prd_mentioned = (
            "PRD" in last_reply
            or "PRD.md" in last_reply
            or "不需要更新" in last_reply
        )
        if not prd_mentioned:
            issues.append(
                "本轮涉及需求变更，但最终回复未说明 PRD 更新情况。"
                "请说明 PRD 更新位置或不需要更新的原因。"
            )

        delivery_keywords = ["影响范围", "验收", "验证结果", "未验证", "回退"]
        missing_delivery = [
            kw for kw in delivery_keywords if kw not in last_reply
        ]
        if len(missing_delivery) >= 3:
            issues.append(
                "本轮涉及新需求/需求变更，但最终回复缺少"
                f"以下交付说明：{', '.join(missing_delivery)}。"
                "请按强制需求处理流程补充完整交付说明。"
            )

    if mentions_flowchart(transcript):
        mermaid_mentioned = (
            "mermaid" in last_reply.lower()
            or "```mermaid" in last_reply
            or "flowchart" in last_reply.lower()
            or "sequenceDiagram" in last_reply
            or "stateDiagram" in last_reply
        )
        if not mermaid_mentioned:
            issues.append(
                "本轮涉及流程图，但未使用 Mermaid 或未说明。"
                "所有流程图必须使用 Mermaid 语法。"
            )

    if "must-fix" not in last_reply and "二次审查" not in last_reply:
        issues.append(
            "未发现二次审查结果。请进行二次审查并输出 must-fix / should-fix / note。"
        )

    if has_frontend_changes(changed_files):
        if "视觉" not in last_reply and "visual" not in last_reply.lower():
            issues.append(
                "有前端改动但未提及视觉审查。"
                "请使用 visual-reviewer 审查或说明为什么不需要。"
            )

    if issues:
        output = {
            "decision": "block",
            "reason": "交付检查未通过，请补充以下内容：\n\n" + "\n\n".join(
                f"{i+1}. {issue}" for i, issue in enumerate(issues)
            ),
        }
    else:
        output = {"decision": "allow"}

    json.dump(output, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
