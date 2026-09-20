import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from stremio_http_proxy.task.optimize_media_task import OptimizeMediaTask


class FakeCacheManager:
    def __init__(self, media_path: Path, status: str = "optimizing"):
        self.media_path = media_path
        self.status = status
        self.ready_sizes = {}

    def get_entry(self, cache_key: str):
        mock_entry = MagicMock()
        mock_entry.status.value = self.status
        return mock_entry

    def parse_cache_key(self, cache_key: str):
        return ("abc123hash", 1)

    def _media_path(self, infohash: str, index: int) -> Path:
        return self.media_path

    def mark_ready(self, cache_key: str, size_bytes: int):
        self.ready_sizes[cache_key] = size_bytes


class FakeLoggerFactory:
    def get_logger(self, name: str, file: str):
        return MagicMock()


@pytest.mark.asyncio
async def test_marks_ready_if_already_mkv_or_mp4(tmp_path):
    media_file = tmp_path / "1.media"
    media_file.write_bytes(b"dummy mp4 content")
    mgr = FakeCacheManager(media_file, status="optimizing")
    logger_factory = FakeLoggerFactory()
    task = OptimizeMediaTask(mgr, logger_factory)

    with patch("stremio_http_proxy.task.optimize_media_task.detect_media_type", return_value=("video/mp4", "mp4")):
        result = await task.run({"cache_key": "abc123hash:1"})

    assert result is True
    assert mgr.ready_sizes["abc123hash:1"] == len(b"dummy mp4 content")


@pytest.mark.asyncio
async def test_remuxes_avi_to_mkv_successfully(tmp_path):
    media_file = tmp_path / "1.media"
    media_file.write_bytes(b"RIFF....AVI ")
    mgr = FakeCacheManager(media_file, status="optimizing")
    logger_factory = FakeLoggerFactory()
    task = OptimizeMediaTask(mgr, logger_factory)

    async def fake_ffmpeg(*args, **kwargs):
        out_file = Path(args[8])
        out_file.write_bytes(b"MATROSKA_MKV_CONTENT")
        proc = MagicMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))
        return proc

    with patch("stremio_http_proxy.task.optimize_media_task.detect_media_type", return_value=("video/x-msvideo", "avi")), \
         patch("asyncio.create_subprocess_exec", side_effect=fake_ffmpeg):
        result = await task.run({"cache_key": "abc123hash:1"})

    assert result is True
    assert media_file.read_bytes() == b"MATROSKA_MKV_CONTENT"
    assert mgr.ready_sizes["abc123hash:1"] == len(b"MATROSKA_MKV_CONTENT")


@pytest.mark.asyncio
async def test_skips_if_status_not_optimizing_or_ready(tmp_path):
    media_file = tmp_path / "1.media"
    media_file.write_bytes(b"downloading content")
    mgr = FakeCacheManager(media_file, status="downloading")
    logger_factory = FakeLoggerFactory()
    task = OptimizeMediaTask(mgr, logger_factory)

    result = await task.run({"cache_key": "abc123hash:1"})

    assert result is True
    assert "abc123hash:1" not in mgr.ready_sizes


@pytest.mark.asyncio
async def test_fallback_to_ready_on_optimization_failure(tmp_path):
    media_file = tmp_path / "1.media"
    original_content = b"ORIGINAL_CORRUPT_OR_WEIRD_FILE"
    media_file.write_bytes(original_content)
    mgr = FakeCacheManager(media_file, status="optimizing")
    logger_factory = FakeLoggerFactory()
    task = OptimizeMediaTask(mgr, logger_factory)

    async def fake_failing_ffmpeg(*args, **kwargs):
        proc = MagicMock()
        proc.returncode = 1
        proc.communicate = AsyncMock(return_value=(b"", b"ffmpeg error"))
        return proc

    with patch("stremio_http_proxy.task.optimize_media_task.detect_media_type", return_value=("video/x-msvideo", "avi")), \
         patch("asyncio.create_subprocess_exec", side_effect=fake_failing_ffmpeg):
        result = await task.run({"cache_key": "abc123hash:1"})

    assert result is False
    assert media_file.read_bytes() == original_content
    assert mgr.ready_sizes["abc123hash:1"] == len(original_content)
