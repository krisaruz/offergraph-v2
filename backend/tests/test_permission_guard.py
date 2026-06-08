"""Tests for PermissionGuard source and URL policies."""

import pytest

from app.runtime.permission_guard import FetchPolicy, PermissionGuard


@pytest.fixture
def guard() -> PermissionGuard:
    return PermissionGuard()


def test_can_search_source_always_allowed(guard):
    decision = guard.can_search_source("nowcoder")

    assert decision.allowed is True
    assert decision.policy == FetchPolicy.PUBLIC_SEARCH_ONLY
    assert decision.reason is None


def test_can_fetch_url_allows_normal_public_page(guard):
    decision = guard.can_fetch_url(
        "https://nowcoder.com/discuss/12345",
        "nowcoder",
    )

    assert decision.allowed is True
    assert decision.policy == FetchPolicy.PUBLIC_FETCH_ALLOWED
    assert decision.reason is None


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/login",
        "https://passport.company.com/signin",
        "https://site.com/auth/callback",
        "https://corp.com/sso/redirect",
    ],
)
def test_can_fetch_url_blocks_login_pages(guard, url):
    decision = guard.can_fetch_url(url, "search_engine")

    assert decision.allowed is False
    assert decision.policy == FetchPolicy.LOGIN_REQUIRED_BLOCKED
    assert decision.reason == "URL appears to require login"


@pytest.mark.parametrize(
    "url",
    [
        "https://example.com/vip/article/1",
        "https://site.com/premium/content",
        "https://news.com/paywall/story",
        "https://media.com/subscribe/only",
    ],
)
def test_can_fetch_url_blocks_paid_content(guard, url):
    decision = guard.can_fetch_url(url, "search_engine")

    assert decision.allowed is False
    assert decision.policy == FetchPolicy.PAID_CONTENT_BLOCKED
    assert decision.reason == "URL appears to be paid content"


def test_can_fetch_url_case_insensitive_matching(guard):
    decision = guard.can_fetch_url("https://Example.COM/LOGIN/page", "nowcoder")

    assert decision.allowed is False
    assert decision.policy == FetchPolicy.LOGIN_REQUIRED_BLOCKED
