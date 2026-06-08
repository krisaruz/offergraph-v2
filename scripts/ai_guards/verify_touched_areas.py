#!/usr/bin/env python3
"""
根据改动文件建议验证命令。

检查 git diff 中的文件，根据改动区域输出建议的验证命令和检查项。
帮助开发者快速定位应该运行哪些验证。

兼容 Windows。

用法:
    python scripts/ai_guards/verify_touched_areas.py
"""

import subprocess
import sys
import os

PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)


def get_changed_files() -> list[str]:
    """获取所有变更文件。"""
    files = set()
    try:
        for cmd in [
            ["git", "diff", "--name-only"],
            ["git", "diff", "--name-only", "--cached"],
        ]:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=10, cwd=PROJECT_ROOT,
            )
            for f in result.stdout.strip().split("\n"):
                if f.strip():
                    files.add(f.strip())
    except Exception:
        pass
    return list(files)


def categorize_changes(files: list[str]) -> dict[str, list[str]]:
    """将变更文件按区域分类。"""
    categories: dict[str, list[str]] = {
        "backend_general": [],
        "api": [],
        "runtime": [],
        "adapter": [],
        "model_schema": [],
        "llm": [],
        "tools": [],
        "frontend": [],
        "config": [],
        "test": [],
        "docs": [],
    }

    for f in files:
        if "backend/app/api/" in f or "routes_" in f:
            categories["api"].append(f)
        elif "backend/app/runtime/" in f:
            categories["runtime"].append(f)
        elif "backend/app/adapters/" in f:
            categories["adapter"].append(f)
        elif "backend/app/models/" in f or "backend/app/schemas/" in f:
            categories["model_schema"].append(f)
        elif "backend/app/llm/" in f:
            categories["llm"].append(f)
        elif "backend/app/tools/" in f:
            categories["tools"].append(f)
        elif "frontend/" in f:
            categories["frontend"].append(f)
        elif "backend/" in f and f.endswith(".py"):
            categories["backend_general"].append(f)
        elif f.endswith((".yml", ".yaml", ".toml", ".json", ".env")):
            categories["config"].append(f)
        elif "test" in f.lower():
            categories["test"].append(f)
        elif f.endswith(".md"):
            categories["docs"].append(f)

    return {k: v for k, v in categories.items() if v}


def suggest_verification(categories: dict[str, list[str]]) -> list[str]:
    """根据变更区域生成验证建议。"""
    suggestions = []

    has_backend = any(
        k in categories
        for k in ["backend_general", "api", "runtime", "adapter", "model_schema", "llm", "tools"]
    )

    if has_backend:
        suggestions.append("【后端测试】cd backend && pytest tests/ -v")

    if "api" in categories:
        suggestions.append("【API 验证】")
        suggestions.append("  - 测试正常请求（200 响应、字段完整）")
        suggestions.append("  - 测试错误请求（400/422 参数校验）")
        suggestions.append("  - 测试边界参数（空值、超长、特殊字符）")
        suggestions.append("  - 检查响应是否与 Pydantic schema 一致")

    if "runtime" in categories:
        suggestions.append("【Runtime 验证】")
        suggestions.append("  - 测试完整搜索链路（API → Runtime → Adapter → Ranker）")
        suggestions.append("  - 测试异常分支（单源失败、全源超时）")
        suggestions.append("  - 测试单源失败容错（asyncio.gather return_exceptions）")

    if "adapter" in categories:
        suggestions.append("【Adapter 验证】")
        suggestions.append("  - 测试正常返回")
        suggestions.append("  - 测试空结果")
        suggestions.append("  - 测试超时处理")
        suggestions.append("  - 测试 Cookie 失效")
        suggestions.append("  - 测试解析异常（格式变化）")

    if "model_schema" in categories:
        suggestions.append("【模型/Schema 验证】")
        suggestions.append("  - 测试字段完整性和默认值")
        suggestions.append("  - 测试序列化/反序列化")
        suggestions.append("  - 检查向前兼容性")
        suggestions.append("  - 检查数据库表结构是否需要迁移")
        suggestions.append("  - 确认已备份 offergraph.db")

    if "llm" in categories:
        suggestions.append("【LLM 验证】")
        suggestions.append("  - 测试正常抽取")
        suggestions.append("  - 测试空文档输入")
        suggestions.append("  - 测试格式错误响应")
        suggestions.append("  - 测试不确定信息处理")
        suggestions.append("  - 检查 Prompt 变更是否同步 PRD")

    if "frontend" in categories:
        suggestions.append("【前端验证】")
        suggestions.append("  - cd frontend && npx tsc --noEmit")
        suggestions.append("  - cd frontend && npm run lint")
        suggestions.append("  - cd frontend && npm run build")
        suggestions.append("  - 启动页面并在浏览器/Electron 窗口中验证")
        suggestions.append("  - 检查 loading / empty / error / success 状态")
        suggestions.append("  - 检查控制台无明显错误")
        suggestions.append("  - 使用 visual-reviewer 审查视觉质量")

    if "config" in categories:
        suggestions.append("【配置验证】")
        suggestions.append("  - 确认配置变更不影响现有功能")
        suggestions.append("  - 确认环境变量文档已更新")

    return suggestions


def main():
    changed_files = get_changed_files()

    if not changed_files:
        print("没有检测到文件变更。")
        sys.exit(0)

    print(f"[INFO] 检测到 {len(changed_files)} 个文件变更：")
    print()
    for f in sorted(changed_files):
        print(f"  {f}")
    print()

    categories = categorize_changes(changed_files)

    if not categories:
        print("无法识别变更区域。请手动确定验证范围。")
        sys.exit(0)

    suggestions = suggest_verification(categories)

    print("=" * 60)
    print("建议验证命令和检查项：")
    print("=" * 60)
    print()
    for s in suggestions:
        print(s)
    print()


if __name__ == "__main__":
    main()
