"""Check XHS session validity via different endpoints"""
import asyncio
import sys
sys.stdout.reconfigure(encoding='utf-8')

import httpx
from app.config import settings


async def test():
    cookie = settings.xhs_cookie

    # Extract key cookie values
    parts = {}
    for p in cookie.split(";"):
        p = p.strip()
        if "=" in p:
            k, v = p.split("=", 1)
            parts[k.strip()] = v.strip()

    print("=== Cookie 关键字段 ===")
    print(f"  web_session: {parts.get('web_session', 'MISSING')[:20]}... (len={len(parts.get('web_session', ''))})")
    print(f"  a1: {parts.get('a1', 'MISSING')[:20]}... (len={len(parts.get('a1', ''))})")
    print(f"  webId: {parts.get('webId', 'MISSING')}")
    print()

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Cookie": cookie,
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.xiaohongshu.com",
        "Referer": "https://www.xiaohongshu.com/",
    }

    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
        # Test 1: User info (checks if session is valid at all)
        print("=== Test 1: 用户信息 API ===")
        try:
            resp = await client.get(
                "https://edith.xiaohongshu.com/api/sns/web/v1/user/selfinfo",
                headers=headers,
            )
            data = resp.json()
            print(f"  Status: {resp.status_code}")
            print(f"  success: {data.get('success')}, code: {data.get('code')}, msg: {data.get('msg')}")
            if data.get("success") and data.get("data"):
                user = data["data"]
                print(f"  用户: {user.get('nickname', 'unknown')}")
        except Exception as e:
            print(f"  Error: {e}")

        # Test 2: Explore page (SSR, less strict)
        print()
        print("=== Test 2: Explore 页面 (SSR) ===")
        try:
            resp = await client.get(
                "https://www.xiaohongshu.com/explore",
                headers={**headers, "Accept": "text/html,application/xhtml+xml"},
            )
            print(f"  Status: {resp.status_code}")
            has_state = "__INITIAL_STATE__" in resp.text
            print(f"  Has __INITIAL_STATE__: {has_state}")
            if has_state:
                print(f"  Cookie 对 SSR 页面有效")
        except Exception as e:
            print(f"  Error: {e}")

        # Test 3: Homefeed API (another API endpoint)
        print()
        print("=== Test 3: Homefeed API ===")
        try:
            resp = await client.get(
                "https://edith.xiaohongshu.com/api/sns/web/v1/homefeed?cursor_score=&num=5&refresh_type=1&note_index=0&unread_begin_note_id=&unread_end_note_id=&unread_note_count=0",
                headers=headers,
            )
            data = resp.json()
            print(f"  Status: {resp.status_code}")
            print(f"  success: {data.get('success')}, code: {data.get('code')}, msg: {data.get('msg')}")
        except Exception as e:
            print(f"  Error: {e}")


if __name__ == "__main__":
    asyncio.run(test())
