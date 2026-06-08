#!/usr/bin/env python3
"""
PRD 同步检查脚本。

检查 git diff 和 staged files，如果有需要同步 PRD 的改动
（API、模型、schema、runtime、adapter、LLM、前端页面等），
但 PRD.md 没有变更，返回非 0 退出码并输出提醒。

可在 CI 或手动执行时使用。
兼容 Windows。

用法:
    python scripts/ai_guards/check_prd_sync.py
"""

import subprocess
import sys
import os

# 项目根目录
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

# 需要 PRD 同步的文件路径模式
PRD_SYNC_PATTERNS = [
    # 后端 API
    "backend/app/api/",
    "routes_",
    # 数据模型
    "backend/app/models/",
    "backend/app/schemas/",
    # Agent Runtime
    "backend/app/runtime/",
    # Source Adapter
    "backend/app/adapters/",
    # LLM
    "backend/app/llm/",
    # 工具层
    "backend/app/tools/",
    # 前端页面
    "frontend/app/",
    "frontend/src/app/",
    "frontend/pages/",
    "frontend/src/pages/",
    # 配置
    "backend/app/config.py",
]


def get_changed_files() -> list[str]:
    """获取所有变更文件（staged + unstaged + untracked）。"""
    files = set()
    try:
        # unstaged changes
        result = subprocess.run(
            ["git", "diff", "--name-only"],
            capture_output=True, text=True, timeout=10, cwd=PROJECT_ROOT,
        )
        for f in result.stdout.strip().split("\n"):
            if f.strip():
                files.add(f.strip())

        # staged changes
        result = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            capture_output=True, text=True, timeout=10, cwd=PROJECT_ROOT,
        )
        for f in result.stdout.strip().split("\n"):
            if f.strip():
                files.add(f.strip())

    except Exception as e:
        print(f"警告：无法获取 git diff: {e}", file=sys.stderr)
        return []

    return list(files)


def needs_prd_sync(files: list[str]) -> list[str]:
    """判断哪些文件改动需要同步 PRD。"""
    matching = []
    for f in files:
        for pattern in PRD_SYNC_PATTERNS:
            if pattern in f:
                matching.append(f)
                break
    return matching


def prd_is_changed(files: list[str]) -> bool:
    """判断 PRD.md 是否在变更列表中。"""
    return any(f.endswith("PRD.md") for f in files)


def main():
    changed_files = get_changed_files()

    if not changed_files:
        print("[OK] 没有检测到文件变更。")
        sys.exit(0)

    files_needing_sync = needs_prd_sync(changed_files)

    if not files_needing_sync:
        print("[OK] 当前改动不涉及需要 PRD 同步的模块。")
        sys.exit(0)

    if prd_is_changed(changed_files):
        print("[OK] PRD.md 已包含在变更中。")
        sys.exit(0)

    # 有需要同步的改动但 PRD 未变更
    print("[WARN] 以下文件改动可能需要同步 PRD.md：")
    print()
    for f in files_needing_sync:
        print(f"  - {f}")
    print()
    print("请检查是否需要更新 PRD.md 中对应的章节。")
    print("如果确认不需要更新 PRD，请在交付说明中说明原因。")
    sys.exit(1)


if __name__ == "__main__":
    main()
