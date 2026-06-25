import json

from app.runtime.source_auth import SourceAuthManager


def test_source_auth_reads_playwright_storage_state(tmp_path):
    state_dir = tmp_path / "auth"
    state_dir.mkdir()
    (state_dir / "maimai_storage_state.json").write_text(
        json.dumps({
            "cookies": [
                {"name": "sid", "value": "fresh", "domain": ".maimai.cn"},
                {"name": "ignore", "value": "x", "domain": ".example.com"},
            ]
        }),
        encoding="utf-8",
    )
    manager = SourceAuthManager(state_dir=state_dir)

    cookie = manager.refresh_cookie("maimai", domains=("maimai.cn",))

    assert cookie == "sid=fresh"
    assert (state_dir / "maimai_cookie.txt").read_text(encoding="utf-8") == "sid=fresh"
    assert manager.has_cookie_state("maimai", domains=("maimai.cn",)) is True


def test_source_auth_merges_set_cookie_headers(tmp_path):
    manager = SourceAuthManager(state_dir=tmp_path / "auth")

    cookie = manager.update_from_set_cookie(
        "maimai",
        "sid=old; csrftoken=abc",
        ["sid=fresh; Path=/; HttpOnly", "new_token=xyz; Path=/"],
    )

    assert cookie == "sid=fresh; csrftoken=abc; new_token=xyz"
    assert (tmp_path / "auth" / "maimai_cookie.txt").read_text(encoding="utf-8") == cookie


def test_mark_validated_records_timestamp(tmp_path):
    manager = SourceAuthManager(state_dir=tmp_path / "auth")

    assert manager.last_validated_at("maimai") is None

    manager.mark_validated("maimai")
    ts = manager.last_validated_at("maimai")

    assert ts is not None
    assert ts > 0
    # second call should move timestamp forward (or equal)
    manager.mark_validated("maimai")
    assert manager.last_validated_at("maimai") >= ts


def test_last_validated_at_returns_none_for_unknown_source(tmp_path):
    manager = SourceAuthManager(state_dir=tmp_path / "auth")
    assert manager.last_validated_at("never_seen") is None
