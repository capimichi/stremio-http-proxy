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
async def test_download_media_task_download_hls_command(fake_logger_factory, tmp_path):
    torrserver_client = MagicMock()
    cache_manager = MagicMock()
    fake_target = tmp_path / "target.tmp"
    fake_target.write_bytes(b"x" * 200)
    cache_manager.prepare_download_path.return_value = fake_target
    cache_manager.get_min_cache_size.return_value = 100

    task = DownloadMediaTask(torrserver_client, cache_manager, fake_logger_factory)

    async def fake_wait():
        fake_target.write_bytes(b"x" * 200)
        return 0

    mock_proc = MagicMock()
    mock_proc.wait = AsyncMock(side_effect=fake_wait)
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    mock_proc.returncode = 0

    with patch("asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)) as mock_exec:
        await task._download_hls("key1:0", "https://upstream.example/live.m3u8")

        mock_exec.assert_called_once()
        cmd = mock_exec.call_args[0]
        assert cmd[0] == "yt-dlp"
        assert "--downloader-args" in cmd
        assert "ffmpeg_i:-allowed_extensions ALL -allowed_segment_extensions ALL -extension_picky 0" in cmd
        assert "--all-formats" in cmd
        assert "--merge-output-format" in cmd
        assert "mkv" in cmd
        assert cmd[-1] == "https://upstream.example/live.m3u8"


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


@pytest.mark.asyncio
async def test_download_media_task_cascades_on_prefetch_failure(fake_logger_factory):
    torrserver_client = MagicMock()
    cache_manager = MagicMock()
    cache_manager.is_ready.return_value = False
    entry = CacheEntry(
        cache_key="hash123:1",
        infohash="hash123",
        cache_index=1,
        source_link="magnet:?xt=urn:btih:hash123",
        title="Sample",
        content_id="tt123:1:2",
        content_type="series",
        category="tv",
        trigger="next_episode_prefetch",
        file_path="/tmp/test",
        tmp_path="/tmp/test.tmp",
    )
    cache_manager.get_entry.return_value = entry
    mock_prefetch_service = AsyncMock()

    task = DownloadMediaTask(
        torrserver_client,
        cache_manager,
        fake_logger_factory,
        next_episode_prefetch_service=mock_prefetch_service,
    )
    task._download_torrent = AsyncMock(side_effect=RuntimeError("swarm dead"))

    with pytest.raises(RuntimeError):
        await task.execute("hash123:1")

    cache_manager.mark_failed.assert_called_once()
    mock_prefetch_service.on_download_failed.assert_awaited_once_with("series", "tt123:1:2", "tv")


@pytest.mark.asyncio
async def test_download_media_task_cascades_on_playback_failure(fake_logger_factory):
    torrserver_client = MagicMock()
    cache_manager = MagicMock()
    cache_manager.is_ready.return_value = False
    entry = CacheEntry(
        cache_key="hash456:1",
        infohash="hash456",
        cache_index=1,
        source_link="magnet:?xt=urn:btih:hash456",
        title="Sample Playback",
        content_id="tt456:2:1",
        content_type="series",
        category="tv",
        trigger="playback",
        file_path="/tmp/test",
        tmp_path="/tmp/test.tmp",
    )
    cache_manager.get_entry.return_value = entry
    mock_prefetch_service = AsyncMock()

    task = DownloadMediaTask(
        torrserver_client,
        cache_manager,
        fake_logger_factory,
        next_episode_prefetch_service=mock_prefetch_service,
    )
    task._download_torrent = AsyncMock(side_effect=RuntimeError("timeout reading torrent"))

    with pytest.raises(RuntimeError):
        await task.execute("hash456:1")

    cache_manager.mark_failed.assert_called_once()
    mock_prefetch_service.on_download_failed.assert_awaited_once_with("series", "tt456:2:1", "tv")
