import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from stremio_http_proxy.enum.cache_entry_status_enum import CacheEntryStatusEnum
from stremio_http_proxy.model.cache_entry import CacheEntry
from stremio_http_proxy.task.download_media_task import DownloadMediaTask


@pytest.fixture
def fake_logger_factory():
    logger_factory = MagicMock()
    logger = MagicMock()
    logger_factory.get_logger.return_value = logger
    return logger_factory


def test_download_media_task_skips_if_already_ready(fake_logger_factory):
    torrserver_client = MagicMock()
    cache_manager = MagicMock()
    cache_manager.is_ready.return_value = True

    task = DownloadMediaTask(torrserver_client, cache_manager, fake_logger_factory)
    result = task.run("hash123:1")

    assert result is True
    assert not torrserver_client.build_download_url.called


def test_download_media_task_skips_if_no_source_link(fake_logger_factory):
    torrserver_client = MagicMock()
    cache_manager = MagicMock()
    cache_manager.is_ready.return_value = False
    cache_manager.get_entry.return_value = CacheEntry(
        cache_key="hash123:1",
        infohash="hash123",
        cache_index=1,
        source_link=None,
        file_path="/tmp/test",
        tmp_path="/tmp/test.tmp",
    )

    task = DownloadMediaTask(torrserver_client, cache_manager, fake_logger_factory)
    result = task.run("hash123:1")

    assert result is False


@pytest.mark.asyncio
async def test_download_media_task_dispatches_hls_ffmpeg(fake_logger_factory, tmp_path):
    torrserver_client = MagicMock()
    cache_manager = MagicMock()
    cache_manager.is_ready.return_value = False
    cache_manager.get_entry.return_value = CacheEntry(
        cache_key="hash123:1",
        infohash="hash123",
        cache_index=1,
        source_link="https://upstream.example/stream.m3u8",
        file_path="/tmp/test",
        tmp_path="/tmp/test.tmp",
    )
    cache_manager.finalize_download.return_value = 10485760

    task = DownloadMediaTask(torrserver_client, cache_manager, fake_logger_factory)
    task._download_hls = AsyncMock()
    task._on_download_completed = MagicMock()

    result = await task.execute("hash123:1")

    assert result is True
    task._download_hls.assert_called_once_with("hash123:1", "https://upstream.example/stream.m3u8")
    cache_manager.finalize_download.assert_called_once_with("hash123:1")
    task._on_download_completed.assert_called_once_with("hash123:1", 10485760)


@pytest.mark.asyncio
async def test_download_media_task_handles_torrent_and_triggers_optimize(fake_logger_factory):
    torrserver_client = MagicMock()
    torrserver_client.build_download_url.return_value = "http://torrserver:8090/stream?link=magnet..."
    cache_manager = MagicMock()
    cache_manager.is_ready.return_value = False
    entry = CacheEntry(
        cache_key="hash123:1",
        infohash="hash123",
        cache_index=1,
        source_link="magnet:?xt=urn:btih:hash123",
        title="Sample",
        poster=None,
        category="movie",
        file_path="/tmp/test",
        tmp_path="/tmp/test.tmp",
    )
    cache_manager.get_entry.return_value = entry
    cache_manager.finalize_download.return_value = 52428800

    task = DownloadMediaTask(torrserver_client, cache_manager, fake_logger_factory)
    task._download_http = AsyncMock()

    with patch("stremio_http_proxy.task.optimize_media_task.optimize_media_task.apply_async") as mock_opt:
        result = await task.execute("hash123:1")
        assert result is True
        cache_manager.mark_optimizing.assert_called_once_with("hash123:1", 52428800)
        mock_opt.assert_called_once_with(args=["hash123:1"], queue="transcode")
