"""Test XHS hybrid search strategy"""
import asyncio
import sys
sys.stdout.reconfigure(encoding='utf-8')

from app.adapters import get_registered_adapters
from app.adapters.base import SourceQuery


async def test():
    adapters = get_registered_adapters()
    xhs = adapters.get("xiaohongshu")
    if not xhs:
        print("XHS adapter not found")
        return

    query = SourceQuery(
        query="字节跳动 后端 面经",
        company="字节跳动",
        position="后端开发",
    )

    print("搜索中 (API -> 回退 explore+filter)...")
    results = await xhs.search(query)
    print(f"\n最终结果: {len(results)} 条")
    for i, r in enumerate(results[:10]):
        print(f"  [{i+1}] {r.title[:60]}")


if __name__ == "__main__":
    asyncio.run(test())
