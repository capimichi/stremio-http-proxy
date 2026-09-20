from unittest.mock import MagicMock
from fastapi.testclient import TestClient
import pytest
from fastapi import FastAPI

from stremio_http_proxy.controller.hub_controller import HubController
from stremio_http_proxy.service.basic_auth_service import BasicAuthService
from stremio_http_proxy.service.hub_service import HubService


@pytest.fixture
def mock_hub_service():
    return MagicMock(spec=HubService)


@pytest.fixture
def auth_service():
    return BasicAuthService()



@pytest.fixture
def client(mock_hub_service, auth_service):
    controller = HubController(
        hub_service=mock_hub_service,
        basic_auth_service=auth_service,
    )
    app = FastAPI()
    app.include_router(controller.router)
    return TestClient(app)


def test_get_recent_media_endpoint(client, mock_hub_service):
    mock_hub_service.get_recent_media.return_value = [
        {"content_id": "tt123", "title": "Test Title", "status": "ready"}
    ]
    resp = client.get("/api/hub/recent?limit=5")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["items"][0]["content_id"] == "tt123"


def test_get_media_streams_endpoint(client, mock_hub_service):
    mock_hub_service.get_media_streams.return_value = [
        {"infohash": "hash1", "status": "downloading"}
    ]
    resp = client.get("/api/hub/media-streams/tt123:1:1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["content_id"] == "tt123:1:1"
    assert len(data["streams"]) == 1


def test_cache_season_endpoint(client, mock_hub_service):
    mock_hub_service.cache_season.return_value = {
        "success": True,
        "content_id": "tt123",
        "season": 1,
        "total_episodes": 10,
        "enqueued_count": 10,
    }
    resp = client.post(
        "/api/browser/cache-season",
        json={"content_id": "tt123", "season": 1, "total_episodes": 10},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_cache_episode_endpoint(client, mock_hub_service):
    mock_hub_service.cache_episode.return_value = {
        "success": True,
        "content_id": "tt123:1:2",
    }
    resp = client.post(
        "/api/browser/cache-episode",
        json={"content_id": "tt123", "season": 1, "episode": 2, "content_type": "series"},
    )
    assert resp.status_code == 200
    assert resp.json()["success"] is True


def test_delete_stream_endpoint(client, mock_hub_service):
    mock_hub_service.delete_stream.return_value = {
        "success": True,
        "cache_key": "abc:1",
    }
    resp = client.delete("/api/hub/streams/abc:1")
    assert resp.status_code == 200
    assert resp.json()["cache_key"] == "abc:1"


def test_get_season_cache_endpoint(client, mock_hub_service):
    mock_hub_service.get_season_cache_status.return_value = {
        1: {"status": "ready", "progress_percent": 100.0, "cache_key": "k1"},
        2: {"status": "downloading", "progress_percent": 50.0, "cache_key": "k2"},
    }
    resp = client.get("/api/hub/season-cache/tt123/1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["content_id"] == "tt123"
    assert data["season"] == 1
    assert data["episodes"]["1"]["status"] == "ready"
    assert data["episodes"]["2"]["status"] == "downloading"


def test_get_tasks_endpoint(client, mock_hub_service):
    mock_hub_service.get_tasks.return_value = [
        {"id": 1, "name": "fetch_next_episode", "status": "pending"}
    ]
    resp = client.get("/api/hub/tasks?limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 1
    assert data["tasks"][0]["id"] == 1


