from __future__ import annotations

from unittest.mock import patch

import pytest


@pytest.mark.asyncio
async def test_report_source_connection_status_requires_all_key_sources(client):
    with patch("app.api.routes_reports._get_adapters", return_value={}):
        response = await client.get("/api/source-connections/status")

    assert response.status_code == 200
    data = response.json()
    assert {item["source"] for item in data} == {"xiaohongshu", "maimai", "nowcoder"}
    assert all(item["status"] == "not_connected" for item in data)


@pytest.mark.asyncio
async def test_create_report_blocks_when_required_sources_missing(client):
    with patch("app.api.routes_reports._get_adapters", return_value={}):
        response = await client.post(
            "/api/reports",
            json={
                "company": "字节跳动",
                "roleDirection": "后端开发",
                "experienceStage": "social",
            },
        )

    assert response.status_code == 200
    data = response.json()["reportRun"]
    assert data["status"] == "blocked_source_unready"
    assert data["diagnostic"]["blockedSources"]
