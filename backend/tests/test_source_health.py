from app.adapters.base import SourceStatus
from app.runtime.source_health import SourceHealthRegistry, describe_source_status


def test_source_health_maps_auth_failure_to_login_action():
    registry = SourceHealthRegistry()

    status = registry.record_status(
        "maimai",
        SourceStatus.UNAUTHORIZED,
        "Cookie expired",
    )

    assert status["status"] == "unauthorized"
    assert status["nextAction"] == "login"
    assert status["recoverable"] is True
    assert status["failureCount"] == 1
    assert status["cooldownSeconds"] == 0


def test_source_health_cools_down_transient_failures():
    now = [100.0]
    registry = SourceHealthRegistry(now_fn=lambda: now[0])

    status = registry.record_status("xiaohongshu", SourceStatus.TIMEOUT, "MCP timeout")

    assert status["nextAction"] == "retry_later"
    # xiaohongshu has per-source override: TIMEOUT = 120s
    assert status["cooldownSeconds"] == 120
    assert registry.is_available("xiaohongshu") is False

    now[0] += 121

    assert registry.is_available("xiaohongshu") is True
    assert registry.cooldown_status("xiaohongshu") is None


def test_source_health_success_resets_failure_count():
    registry = SourceHealthRegistry()
    registry.record_status("search_engine", SourceStatus.ERROR, "network error")

    status = registry.record_status("search_engine", SourceStatus.OK, None)

    assert status["status"] == "ok"
    assert status["failureCount"] == 0
    assert status["nextAction"] == "none"


def test_describe_source_status_maps_config_error_to_configure():
    status = describe_source_status(
        "search_engine",
        SourceStatus.CONFIG_ERROR,
        "SEARXNG_BASE_URL is missing",
    )

    assert status["status"] == "config_error"
    assert status["nextAction"] == "configure"
    assert status["recoverable"] is True
