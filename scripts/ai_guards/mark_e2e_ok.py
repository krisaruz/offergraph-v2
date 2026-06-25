#!/usr/bin/env python3
"""
端到端验收通过标记生成器。

在完成端到端关键链路验证和真实效果自验后运行此脚本，
生成 .e2e-ok marker 文件，供 validate_before_stop.py 校验。

marker 包含当前 diff hash，diff 变化后自动失效。

用法：
    python scripts/ai_guards/mark_e2e_ok.py
"""

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from typing import List


def get_project_root() -> str:
    return os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )


def get_changed_files(project_root: str) -> List[str]:
    """获取当前 diff 文件列表。"""
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, timeout=10, cwd=project_root, encoding="utf-8", errors="replace",
        )
        files = [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]

        result2 = subprocess.run(
            ["git", "diff", "--name-only", "--cached"],
            capture_output=True, text=True, timeout=10, cwd=project_root, encoding="utf-8", errors="replace",
        )
        staged = [f.strip() for f in result2.stdout.strip().split("\n") if f.strip()]

        return list(set(files + staged))
    except Exception:
        return []


def get_diff_hash(project_root: str) -> str:
    """计算当前 diff 内容的哈希值。"""
    try:
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            capture_output=True, text=True, timeout=30, cwd=project_root, encoding="utf-8", errors="replace",
        )
        diff_content = result.stdout

        result2 = subprocess.run(
            ["git", "diff", "--cached"],
            capture_output=True, text=True, timeout=30, cwd=project_root, encoding="utf-8", errors="replace",
        )
        diff_content += result2.stdout

        return hashlib.sha256(diff_content.encode("utf-8")).hexdigest()[:16]
    except Exception:
        return "no-diff"


# 实质修改判断（与 validate_before_stop.py 保持一致）
SUBSTANTIVE_PREFIXES = [
    "backend/app/", "frontend/src/", "electron/",
    "scripts/", "config/",
    "package.json", "pnpm-lock.yaml", "package-lock.json", "yarn.lock",
    "PRD.md", "CLAUDE.md", "AGENTS.md",
]
SUBSTANTIVE_EXTENSIONS = [
    ".py", ".ts", ".tsx", ".js", ".jsx", ".css", ".scss", ".vue",
]
EXCLUDED_PREFIXES = [
    ".claude/", ".cursor/", ".codex/",
    "docs/", "README", "LICENSE",
]


def is_substantive_change(files: List[str]) -> bool:
    for f in files:
        is_excluded = any(f.startswith(ex) or f == ex.rstrip("/") for ex in EXCLUDED_PREFIXES)
        if is_excluded:
            continue
        for prefix in SUBSTANTIVE_PREFIXES:
            if f.startswith(prefix) or f == prefix.rstrip("/"):
                return True
        for ext in SUBSTANTIVE_EXTENSIONS:
            if f.endswith(ext):
                return True
    return False


def main():
    project_root = get_project_root()
    changed_files = get_changed_files(project_root)

    if not changed_files:
        print("当前没有改动，无需创建 marker。")
        sys.exit(0)

    if not is_substantive_change(changed_files):
        print("当前改动不属于实质修改，无需创建 marker。")
        sys.exit(0)

    diff_hash = get_diff_hash(project_root)
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz).isoformat()

    marker_data = {
        "type": "e2e",
        "timestamp": now,
        "diff_hash": diff_hash,
        "changed_files": sorted(changed_files),
        "file_count": len(changed_files),
    }

    marker_path = os.path.join(project_root, ".e2e-ok")
    with open(marker_path, "w", encoding="utf-8") as f:
        json.dump(marker_data, f, ensure_ascii=False, indent=2)

    print(f"已生成端到端验收 marker: {marker_path}")
    print(f"  diff hash: {diff_hash}")
    print(f"  文件数: {len(changed_files)}")
    print(f"  时间: {now}")


if __name__ == "__main__":
    main()
