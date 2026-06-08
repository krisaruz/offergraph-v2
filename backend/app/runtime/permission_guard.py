from enum import Enum
from typing import Optional

from pydantic import BaseModel


class FetchPolicy(str, Enum):
    PUBLIC_SEARCH_ONLY = "public_search_only"
    PUBLIC_FETCH_ALLOWED = "public_fetch_allowed"
    LOGIN_REQUIRED_BLOCKED = "login_required_blocked"
    PAID_CONTENT_BLOCKED = "paid_content_blocked"
    USER_AUTHORIZED_COOKIE = "user_authorized_cookie"
    ROBOTS_DISALLOWED = "robots_disallowed"


class PermissionDecision(BaseModel):
    allowed: bool
    policy: FetchPolicy
    reason: Optional[str] = None


class PermissionGuard:
    """
    权限门禁：在搜索、抓取、保存前检查来源权限。
    MVP 阶段以白名单/关键词判断为主，后续接入 robots.txt 解析。
    """

    _LOGIN_KEYWORDS = ("login", "signin", "passport", "auth", "sso")
    _PAID_KEYWORDS = ("vip", "premium", "pay", "subscribe")

    def can_search_source(self, source: str) -> PermissionDecision:
        return PermissionDecision(
            allowed=True,
            policy=FetchPolicy.PUBLIC_SEARCH_ONLY,
            reason=None,
        )

    def can_fetch_url(self, url: str, source: str) -> PermissionDecision:
        url_lower = url.lower()

        if self._looks_like_login_url(url_lower):
            return PermissionDecision(
                allowed=False,
                policy=FetchPolicy.LOGIN_REQUIRED_BLOCKED,
                reason="URL appears to require login",
            )

        if self._looks_like_paid_content(url_lower):
            return PermissionDecision(
                allowed=False,
                policy=FetchPolicy.PAID_CONTENT_BLOCKED,
                reason="URL appears to be paid content",
            )

        return PermissionDecision(
            allowed=True,
            policy=FetchPolicy.PUBLIC_FETCH_ALLOWED,
            reason=None,
        )

    def _looks_like_login_url(self, url: str) -> bool:
        return any(k in url for k in self._LOGIN_KEYWORDS)

    def _looks_like_paid_content(self, url: str) -> bool:
        return any(k in url for k in self._PAID_KEYWORDS)
