"""Tests for application settings."""

from app.config import Settings


def test_settings_default_values():
    settings = Settings(_env_file=None)

    assert settings.search_api_provider == "serpapi"
    assert settings.search_api_key == ""
    assert settings.nowcoder_enabled is True
    assert settings.maimai_enabled is True
    assert settings.xhs_enabled is True
    assert settings.search_timeout_platform == 60
    assert settings.webfetch_timeout == 30
    assert settings.webfetch_max_urls == 10
    assert settings.llm_api_base == "http://ai-gateway.wps.cn/api/v3"
    assert settings.llm_model == "deepseek/deepseek-v4-flash"
    assert settings.database_url == "sqlite+aiosqlite:///./offergraph.db"
    assert settings.host == "127.0.0.1"
    assert settings.port == 8000


def test_settings_custom_override():
    settings = Settings(
        database_url="sqlite+aiosqlite:///:memory:",
        search_api_key="test-key",
        nowcoder_enabled=False,
        llm_api_key="override-key",
        port=9000,
    )

    assert settings.database_url == "sqlite+aiosqlite:///:memory:"
    assert settings.search_api_key == "test-key"
    assert settings.nowcoder_enabled is False
    assert settings.llm_api_key == "override-key"
    assert settings.port == 9000


def test_settings_extra_fields_ignored():
    settings = Settings(_env_file=None)
    dumped = settings.model_dump()

    assert "unknown_field" not in dumped
    assert isinstance(dumped["feed_cache_ttl_hours"], int)
