import time
from unittest.mock import MagicMock
import pytest

from stremio_http_proxy.entity.cache_entry import CacheEntry as CacheEntryRecord
from stremio_http_proxy.enum.cache_entry_status_enum import CacheEntryStatusEnum
from stremio_http_proxy.manager.db_manager import DbManager
from stremio_http_proxy.model.cache_entry import CacheEntry as CacheEntryModel
from stremio_http_proxy.repository.playback_history_repository import PlaybackHistoryRepository
from stremio_http_proxy.service.hub_service import HubService


@pytest.fixture
def db_manager(tmp_path):
    sqlite_file = tmp_path / "test_hub.sqlite"
    return DbManager(str(sqlite_file))


@pytest.fixture
def playback_history_repo(db_manager):
    return PlaybackHistoryRepository(db_manager)


def test_playback_history_record_and_list(playback_history_repo):
    entry1 = playback_history_repo.record_playback(
        content_id="tt0944947:1:1",
        content_type="series",
        title="Game of Thrones S01E01",
        poster="https://example.com/poster.jpg",
        category="tv",
        source_link="magnet:?xt=urn:btih:abc123def456",
        infohash="abc123def456",
        file_index=1,
    )
    assert entry1.id is not None
    assert entry1.content_id == "tt0944947:1:1"

    # Record another playback for same content_id later
    time.sleep(0.01)
    entry2 = playback_history_repo.record_playback(
        content_id="tt0944947:1:2",
        content_type="series",
        title="Game of Thrones S01E02",
    )

    recent = playback_history_repo.list_recent(limit=10)
    assert len(recent) == 2
    assert recent[0].content_id == "tt0944947:1:2"
    assert recent[1].content_id == "tt0944947:1:1"


def test_hub_service_get_recent_media(playback_history_repo):
    playback_history_repo.record_playback(
        content_id="tt111:1:1",
        content_type="series",
        title="Show S01E01",
        poster="https://img.test/p.jpg",
    )

    mock_cache_manager = MagicMock()
    mock_entry = CacheEntryModel(
        cache_key="hash1:1",
        infohash="hash1",
        cache_index=1,
        status=CacheEntryStatusEnum.READY.value,
        title="Show S01E01 1080p",
        size_bytes=1000000000,
        file_path="/tmp/video.mkv",
        tmp_path="/tmp/video.mkv.tmp",
    )
    mock_cache_manager.get_entries_for_content.return_value = [("hash1:1", mock_entry)]
    mock_cache_manager.parse_cache_key.return_value = ("hash1", 1)

    mock_prefetch_service = MagicMock()
    mock_task_service = MagicMock()

    service = HubService(
        playback_history_repository=playback_history_repo,
        cache_manager=mock_cache_manager,
        next_episode_prefetch_service=mock_prefetch_service,
        task_service=mock_task_service,
    )

    recent = service.get_recent_media(limit=5)
    assert len(recent) == 1
    item = recent[0]
    assert item["content_id"] == "tt111:1:1"
    assert item["imdb_id"] == "tt111"
    assert item["season"] == 1
    assert item["episode"] == 1
    assert item["status"] == "ready"
    assert item["streams_count"] == 1
    assert "stremio://detail/series/tt111/1/1" in item["stremio_url"]


def test_hub_service_cache_season(playback_history_repo):
    mock_cache_manager = MagicMock()
    mock_prefetch_service = MagicMock()
    mock_task_service = MagicMock()

    service = HubService(
        playback_history_repository=playback_history_repo,
        cache_manager=mock_cache_manager,
        next_episode_prefetch_service=mock_prefetch_service,
        task_service=mock_task_service,
    )

    res = service.cache_season(content_id="tt999", season=2, total_episodes=5, category="tv")
    assert res["success"] is True
    assert res["enqueued_count"] == 5
    assert mock_task_service.enqueue_task.call_count == 5


def test_hub_service_cache_episode(playback_history_repo):
    mock_cache_manager = MagicMock()
    mock_prefetch_service = MagicMock()
    mock_task_service = MagicMock()

    service = HubService(
        playback_history_repository=playback_history_repo,
        cache_manager=mock_cache_manager,
        next_episode_prefetch_service=mock_prefetch_service,
        task_service=mock_task_service,
    )

    res = service.cache_episode(content_id="tt999", season=2, episode=4, content_type="series")
    assert res["success"] is True
    assert res["content_id"] == "tt999:2:4"
    mock_task_service.enqueue_task.assert_called_once()


def test_hub_service_library(db_manager, playback_history_repo):
    from stremio_http_proxy.repository.media_repository import MediaRepository
    media_repo = MediaRepository(db_manager)
    media_repo.upsert_media("tt0903747", "series", "Breaking Bad", "2008")
    media_repo.upsert_media_item("tt0903747:1:1", "tt0903747", 1, 1, "Pilot")

    mock_cache_manager = MagicMock()
    mock_cache_manager.get_entries_for_content.return_value = []
    service = HubService(
        playback_history_repository=playback_history_repo,
        cache_manager=mock_cache_manager,
        next_episode_prefetch_service=MagicMock(),
        media_repository=media_repo,
    )

    lib = service.get_library()
    assert lib["total"] == 1
    assert lib["items"][0]["title"] == "Breaking Bad"
    assert lib["items"][0]["total_episodes_count"] == 1

    # Delete media
    del_res = service.delete_media("tt0903747")
    assert del_res["success"] is True
    lib_after = service.get_library()
    assert lib_after["total"] == 0


def test_hub_service_get_season_cache_status(playback_history_repo):
    mock_cache_manager = MagicMock()
    mock_entry_ep1 = CacheEntryModel(
        cache_key="hash1:1",
        infohash="hash1",
        cache_index=1,
        content_id="tt999:1:1",
        status=CacheEntryStatusEnum.READY.value,
        title="Show S01E01",
        size_bytes=1000,
        progress_percent=100.0,
        file_path="/tmp/ep1.mkv",
        tmp_path="/tmp/ep1.mkv.tmp",
    )
    mock_entry_ep2 = CacheEntryModel(
        cache_key="hash2:1",
        infohash="hash2",
        cache_index=1,
        content_id="tt999:1:2",
        status=CacheEntryStatusEnum.DOWNLOADING.value,
        title="Show S01E02",
        size_bytes=0,
        progress_percent=45.5,
        file_path="/tmp/ep2.mkv",
        tmp_path="/tmp/ep2.mkv.tmp",
    )
    mock_cache_manager.get_entries_for_content_prefix.return_value = [
        ("hash1:1", mock_entry_ep1),
        ("hash2:1", mock_entry_ep2),
    ]

    service = HubService(
        playback_history_repository=playback_history_repo,
        cache_manager=mock_cache_manager,
        next_episode_prefetch_service=MagicMock(),
    )

    statuses = service.get_season_cache_status("tt999", 1)
    mock_cache_manager.get_entries_for_content_prefix.assert_called_once_with("tt999:1:")
    assert 1 in statuses
    assert statuses[1]["status"] == "ready"
    assert statuses[1]["progress_percent"] == 100.0
    assert 2 in statuses
    assert statuses[2]["status"] == "downloading"
    assert statuses[2]["progress_percent"] == 45.5

