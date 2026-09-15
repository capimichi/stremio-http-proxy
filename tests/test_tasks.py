import asyncio
from unittest.mock import AsyncMock

from stremio_http_proxy.task.fetch_media_task import FetchMediaTask
from stremio_http_proxy.task.fetch_next_episode_task import FetchNextEpisodeTask


def test_fetch_next_episode_task_skips_non_series():
    prefetch_service = AsyncMock()
    prefetch_service.enabled = True
    task = FetchNextEpisodeTask(prefetch_service)

    # 1. Movie content_type returns True (skipped) without calling prefetch_service
    res = asyncio.run(task.run({"content_type": "movie", "content_id": "tt12345"}))
    assert res is True
    assert not prefetch_service.enqueue_next_episode.called

    # 2. Series calls enqueue_next_episode
    prefetch_service.enqueue_next_episode.return_value = True
    res = asyncio.run(task.run({"content_type": "series", "content_id": "tt123:1:2", "category": "tv"}))
    assert res is True
    prefetch_service.enqueue_next_episode.assert_called_once_with("series", "tt123:1:2", "tv")


def test_fetch_media_task_delegates():
    prefetch_service = AsyncMock()
    prefetch_service.enabled = True
    prefetch_service.enqueue_candidate_for_content.return_value = True
    task = FetchMediaTask(prefetch_service)

    res = asyncio.run(task.run({"content_type": "movie", "content_id": "tt0111161", "category": "movie"}))
    assert res is True
    prefetch_service.enqueue_candidate_for_content.assert_called_once_with(
        content_type="movie",
        content_id="tt0111161",
        category="movie",
    )
