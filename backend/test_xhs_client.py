"""Test XhsClient from xiaohongshu-cli"""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from xhs_cli.client import XhsClient
from app.config import settings


def parse_cookies(cookie_str: str) -> dict:
    """Parse cookie string into dict"""
    cookies = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies


def test():
    cookie_dict = parse_cookies(settings.xhs_cookie)
    print(f"Cookie keys: {list(cookie_dict.keys())[:10]}...")
    print(f"a1 present: {'a1' in cookie_dict}")
    print(f"web_session present: {'web_session' in cookie_dict}")
    print()

    client = XhsClient(cookies=cookie_dict, timeout=15.0)
    keyword = "字节跳动 后端 面经"
    print(f"Searching: {keyword}")

    try:
        result = client.search_notes(keyword, page=1, page_size=10)
        print(f"Result type: {type(result)}")

        if isinstance(result, dict):
            if result.get("success"):
                items = result.get("data", {}).get("items", [])
                print(f"Results: {len(items)}")
                for i, item in enumerate(items[:5]):
                    nc = item.get("note_card", {})
                    title = nc.get("display_title", "no title")
                    print(f"  [{i+1}] {title[:60]}")
            else:
                print(f"Error: code={result.get('code')}, msg={result.get('msg')}")
        else:
            print(f"Unexpected result: {str(result)[:300]}")
    except Exception as e:
        print(f"Exception: {type(e).__name__}: {e}")


if __name__ == "__main__":
    test()
