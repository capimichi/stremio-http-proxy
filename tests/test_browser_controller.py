import pytest
from unittest.mock import AsyncMock, MagicMock
from fastapi import HTTPException
from fastapi.testclient import TestClient
from fastapi import FastAPI

from stremio_http_proxy.controller.browser_controller import BrowserController, ImportMediaRequest
from stremio_http_proxy.entity.media import Media
from stremio_http_proxy.entity.media_item import MediaItem
from stremio_http_proxy.manager.db_manager import DbManager
from stremio_http_proxy.manager.jinja_manager import JinjaManager
from stremio_http_proxy.repository.media_item_repository import MediaItemRepository
from stremio_http_proxy.repository.media_repository import MediaRepository
from stremio_http_proxy.service.basic_auth_service import BasicAuthService
from stremio_http_proxy.service.content_browser_service import ContentBrowserService


@pytest.fixture
def db_manager(tmp_path):
    db_file = tmp_path / "test_browser.db"
    mgr = DbManager(f"sqlite:///{db_file}")
    from stremio_http_proxy.entity.base import Base
    with mgr.engine.begin() as conn:
        Base.metadata.create_all(conn)
    return mgr


@pytest.fixture
def media_repo(db_manager):
    return MediaRepository(db_manager)


@pytest.fixture
def media_item_repo(db_manager):
    return MediaItemRepository(db_manager)


@pytest.fixture
def content_browser_service():
    service = MagicMock(spec=ContentBrowserService)
    service.search_content = AsyncMock(return_value={"results": [], "page": 1, "total_pages": 1})
    service.import_media = AsyncMock(return_value={"media_id": 1, "status": "imported"})
    service.refresh_media = AsyncMock(return_value={"success": True, "media_id": 1, "status": "updated"})
    service.browse_content = AsyncMock(return_value={"streams": [{"name": "Stream 1", "infohash": "abc"}]})
    return service


@pytest.fixture
def auth_service():
    auth = MagicMock(spec=BasicAuthService)
    auth.security = MagicMock()
    auth.require_auth = MagicMock()
    return auth


@pytest.fixture
def jinja_manager():
    jm = MagicMock(spec=JinjaManager)
    jm.render = MagicMock(return_value="<html>Rendered</html>")
    return jm


@pytest.fixture
def browser_controller(content_browser_service, auth_service, jinja_manager, media_repo, media_item_repo):
    return BrowserController(
        content_browser_service=content_browser_service,
        basic_auth_service=auth_service,
        jinja_manager=jinja_manager,
        media_repository=media_repo,
        media_item_repository=media_item_repo,
    )


@pytest.mark.asyncio
async def test_browser_detail_page_found(browser_controller, media_repo, media_item_repo, jinja_manager):
    media = media_repo.upsert_media(
        media_type="series",
        title="Breaking Bad",
        imdb_id="tt0903747",
        tmdb_id="1396",
        year="2008",
        overview="A high school chemistry teacher diagnosed with cancer...",
        poster="/media/images/posters/bb.jpg",
    )
    media_item_repo.upsert_media_item(
        media_id=media.id,
        season=1,
        episode=1,
        title="Pilot",
        overview="Walter White begins his descent.",
        thumbnail="/media/images/episodes/bb_1_1.jpg",
    )

    response = await browser_controller.browser_detail_page(media.id)
    assert response.status_code == 200
    assert jinja_manager.render.called
    call_args = jinja_manager.render.call_args[1]
    assert call_args["media"].id == media.id
    assert call_args["media_id"] == media.id
    assert call_args["media_type"] == "series"
    assert call_args["imdb_id"] == "tt0903747"
    assert 1 in call_args["episodes_by_season"]
    assert call_args["episodes_by_season"][1][0]["title"] == "Pilot"


@pytest.mark.asyncio
async def test_browser_detail_page_not_found(browser_controller):
    with pytest.raises(HTTPException) as exc_info:
        await browser_controller.browser_detail_page(99999)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_import_media_endpoint(browser_controller, content_browser_service):
    req = ImportMediaRequest(tmdb_id=1396, type="series")
    res = await browser_controller.import_media(req)
    assert res == {"media_id": 1, "status": "imported"}
    content_browser_service.import_media.assert_awaited_once_with(1396, "series")


@pytest.mark.asyncio
async def test_get_media_streams(browser_controller, media_repo, content_browser_service):
    media = media_repo.upsert_media(
        media_type="movie",
        title="Inception",
        imdb_id="tt1375666",
    )
    res = await browser_controller.get_media_streams(media.id)
    assert "streams" in res
    assert len(res["streams"]) == 1
    content_browser_service.browse_content.assert_awaited_once_with("movie", "tt1375666", None, None)


@pytest.mark.asyncio
async def test_refresh_media_endpoint(browser_controller, content_browser_service):
    res = await browser_controller.refresh_media(1)
    assert res == {"success": True, "media_id": 1, "status": "updated"}
    content_browser_service.refresh_media.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_browser_streams_page_series(browser_controller, media_repo, media_item_repo, jinja_manager):
    media = media_repo.upsert_media(
        media_type="series",
        title="Breaking Bad",
        imdb_id="tt0903747",
    )
    media_item_repo.upsert_media_item(
        media_id=media.id,
        season=2,
        episode=5,
        title="Breakage",
        overview="Walt and Jesse face new problems.",
    )

    response = await browser_controller.browser_streams_page(media.id, season=2, episode=5)
    assert response.status_code == 200
    assert jinja_manager.render.called
    call_args = jinja_manager.render.call_args[1]
    assert call_args["media"].id == media.id
    assert call_args["season"] == 2
    assert call_args["episode"] == 5
    assert call_args["item"].title == "Breakage"
    assert call_args["back_url"] == f"/dashboard/browser/media/{media.id}?season=2"


@pytest.mark.asyncio
async def test_browser_streams_page_movie(browser_controller, media_repo, jinja_manager):
    media = media_repo.upsert_media(
        media_type="movie",
        title="Inception",
        imdb_id="tt1375666",
    )

    response = await browser_controller.browser_streams_page(media.id)
    assert response.status_code == 200
    assert jinja_manager.render.called
    call_args = jinja_manager.render.call_args[1]
    assert call_args["media"].id == media.id
    assert call_args["season"] is None
    assert call_args["episode"] is None
    assert call_args["back_url"] == f"/dashboard/browser/media/{media.id}"


@pytest.mark.asyncio
async def test_browser_streams_page_not_found(browser_controller):
    with pytest.raises(HTTPException) as exc_info:
        await browser_controller.browser_streams_page(99999)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_browse_content_deduplication():
    mock_upstream = MagicMock()
    mock_upstream.get_json = AsyncMock(return_value={
        "streams": [
            {"name": "Stream 1", "infoHash": "abc1234567890123456789012345678901234567", "fileIdx": 1},
            {"name": "Stream 1 Dup", "infoHash": "abc1234567890123456789012345678901234567", "fileIdx": 1},
            {"name": "Stream HLS", "url": "https://example.com/playlist.m3u8"},
            {"name": "Stream HLS Dup", "url": "https://example.com/playlist.m3u8"},
            {"name": "Stream 2", "infoHash": "def1234567890123456789012345678901234567", "fileIdx": 2},
        ]
    })
    mock_tmdb = MagicMock()
    mock_tmdb.get_meta_by_imdb_id = AsyncMock(return_value={"meta": {}})
    mock_rewrite = MagicMock()
    mock_rewrite.rewrite = AsyncMock(side_effect=lambda payload, category, content_type, content_id: payload)
    mock_rewrite._extract_infohash_from_stream = MagicMock(side_effect=lambda s: s.get("infoHash"))

    service = ContentBrowserService(
        upstream_client=mock_upstream,
        tmdb_client=mock_tmdb,
        stream_rewrite_service=mock_rewrite,
    )

    res = await service.browse_content("series", "tt3749900", 2, 18)
    # Rewrite must be called with stream_id "tt3749900:2:18"
    mock_rewrite.rewrite.assert_awaited_once_with(
        mock_upstream.get_json.return_value,
        category="tv",
        content_type="series",
        content_id="tt3749900:2:18",
    )
    # Duplicate torrent and duplicate HLS should be dropped: 5 input -> 3 unique
    assert len(res["streams"]) == 3
    assert res["streams"][0]["name"] == "Stream 1"
    assert res["streams"][1]["name"] == "Stream HLS"
    assert res["streams"][2]["name"] == "Stream 2"


