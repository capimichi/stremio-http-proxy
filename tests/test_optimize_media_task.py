import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from pathlib import Path

from stremio_http_proxy.enum.optimize_media_target_enum import OptimizeMediaTargetEnum
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
async def test_marks_ready_if_already_web_ready_mp4(tmp_path):
    media_file = tmp_path / "1.media"
    media_file.write_bytes(b"dummy mp4 content")
    mgr = FakeCacheManager(media_file, status="optimizing")
    logger_factory = FakeLoggerFactory()
    task = OptimizeMediaTask(mgr, logger_factory, optimize_media_target=OptimizeMediaTargetEnum.WEB_READY_MP4)

    probe_data = {
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p"},
            {"codec_type": "audio", "codec_name": "aac", "channels": 2},
        ]
    }

    with patch("stremio_http_proxy.task.optimize_media_task.detect_media_type", return_value=("video/mp4", "mp4")), \
         patch.object(task, "_probe_media", return_value=probe_data), \
         patch.object(task, "_run_ffmpeg") as mock_ffmpeg:
        result = await task.run({"cache_key": "abc123hash:1"})

    assert result is True
    assert mgr.ready_sizes["abc123hash:1"] == len(b"dummy mp4 content")
    mock_ffmpeg.assert_not_called()


@pytest.mark.asyncio
async def test_remuxes_h264_mkv_to_mp4_with_video_copy(tmp_path):
    media_file = tmp_path / "1.media"
    media_file.write_bytes(b"H264_MKV_CONTENT")
    mgr = FakeCacheManager(media_file, status="optimizing")
    logger_factory = FakeLoggerFactory()
    task = OptimizeMediaTask(mgr, logger_factory, optimize_media_target=OptimizeMediaTargetEnum.WEB_READY_MP4)

    probe_data = {
        "streams": [
            {"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p"},
            {"codec_type": "audio", "codec_name": "ac3", "channels": 6},
        ]
    }

    executed_cmd = []

    async def fake_ffmpeg(cmd):
        executed_cmd.extend(cmd)
        out_file = Path(cmd[-1])
        out_file.write_bytes(b"MP4_OPTIMIZED_CONTENT")
        return True

    with patch("stremio_http_proxy.task.optimize_media_task.detect_media_type", return_value=("video/x-matroska", "mkv")), \
         patch.object(task, "_probe_media", return_value=probe_data), \
         patch.object(task, "_run_ffmpeg", side_effect=fake_ffmpeg):
        result = await task.run({"cache_key": "abc123hash:1"})

    assert result is True
    assert media_file.read_bytes() == b"MP4_OPTIMIZED_CONTENT"
    assert "-c:v" in executed_cmd
    assert executed_cmd[executed_cmd.index("-c:v") + 1] == "copy"
    assert "-c:a" in executed_cmd
    assert executed_cmd[executed_cmd.index("-c:a") + 1] == "aac"
    assert "+faststart" in executed_cmd


@pytest.mark.asyncio
async def test_transcodes_hevc_via_gpu_when_vaapi_available(tmp_path):
    media_file = tmp_path / "1.media"
    media_file.write_bytes(b"HEVC_CONTENT")
    mgr = FakeCacheManager(media_file, status="optimizing")
    logger_factory = FakeLoggerFactory()
    task = OptimizeMediaTask(mgr, logger_factory, optimize_media_target=OptimizeMediaTargetEnum.WEB_READY_MP4)

    probe_data = {
        "streams": [
            {"codec_type": "video", "codec_name": "hevc", "pix_fmt": "yuv420p10le"},
            {"codec_type": "audio", "codec_name": "ac3", "channels": 6},
        ]
    }

    executed_cmd = []

    async def fake_ffmpeg(cmd):
        executed_cmd.extend(cmd)
        out_file = Path(cmd[-1])
        out_file.write_bytes(b"MP4_GPU_ENCODED")
        return True

    with patch("stremio_http_proxy.task.optimize_media_task.detect_media_type", return_value=("video/x-matroska", "mkv")), \
         patch.object(task, "_probe_media", return_value=probe_data), \
         patch.object(task, "_is_vaapi_available", return_value=True), \
         patch.object(task, "_run_ffmpeg", side_effect=fake_ffmpeg):
        result = await task.run({"cache_key": "abc123hash:1"})

    assert result is True
    assert media_file.read_bytes() == b"MP4_GPU_ENCODED"
    assert "-c:v" in executed_cmd
    assert executed_cmd[executed_cmd.index("-c:v") + 1] == "h264_vaapi"
    assert "-vf" in executed_cmd
    assert executed_cmd[executed_cmd.index("-vf") + 1] == "scale_vaapi=format=nv12"
    assert "-hwaccel" in executed_cmd


@pytest.mark.asyncio
async def test_transcodes_hevc_falls_back_to_cpu_when_gpu_fails(tmp_path):
    media_file = tmp_path / "1.media"
    media_file.write_bytes(b"HEVC_CONTENT")
    mgr = FakeCacheManager(media_file, status="optimizing")
    logger_factory = FakeLoggerFactory()
    task = OptimizeMediaTask(mgr, logger_factory, optimize_media_target=OptimizeMediaTargetEnum.WEB_READY_MP4)

    probe_data = {
        "streams": [
            {"codec_type": "video", "codec_name": "hevc", "pix_fmt": "yuv420p10le"},
            {"codec_type": "audio", "codec_name": "aac", "channels": 2},
        ]
    }

    calls = []

    async def fake_ffmpeg(cmd):
        calls.append(cmd)
        if "h264_vaapi" in cmd:
            return False  # GPU failed
        out_file = Path(cmd[-1])
        out_file.write_bytes(b"MP4_CPU_ENCODED")
        return True

    with patch("stremio_http_proxy.task.optimize_media_task.detect_media_type", return_value=("video/x-matroska", "mkv")), \
         patch.object(task, "_probe_media", return_value=probe_data), \
         patch.object(task, "_is_vaapi_available", return_value=True), \
         patch.object(task, "_run_ffmpeg", side_effect=fake_ffmpeg):
        result = await task.run({"cache_key": "abc123hash:1"})

    assert result is True
    assert media_file.read_bytes() == b"MP4_CPU_ENCODED"
    assert len(calls) == 2
    assert "h264_vaapi" in calls[0]
    assert "libx264" in calls[1]


@pytest.mark.asyncio
async def test_skips_when_optimization_disabled(tmp_path):
    media_file = tmp_path / "1.media"
    media_file.write_bytes(b"RAW_VIDEO_CONTENT")
    mgr = FakeCacheManager(media_file, status="optimizing")
    logger_factory = FakeLoggerFactory()
    task = OptimizeMediaTask(mgr, logger_factory, optimize_media_enabled=False)

    with patch.object(task, "_probe_media") as mock_probe:
        result = await task.run({"cache_key": "abc123hash:1"})

    assert result is True
    assert mgr.ready_sizes["abc123hash:1"] == len(b"RAW_VIDEO_CONTENT")
    mock_probe.assert_not_called()


@pytest.mark.asyncio
async def test_compatible_optimization_runs_fast_remux_with_cues_to_front(tmp_path):
    media_file = tmp_path / "1.media"
    media_file.write_bytes(b"RAW_TORRENT_MKV_OR_AVI")
    mgr = FakeCacheManager(media_file, status="optimizing")
    logger_factory = FakeLoggerFactory()
    task = OptimizeMediaTask(mgr, logger_factory, optimize_media_target=OptimizeMediaTargetEnum.COMPATIBLE)

    executed_cmd = []

    async def fake_ffmpeg(cmd):
        executed_cmd.extend(cmd)
        out_file = Path(cmd[-1])
        out_file.write_bytes(b"OPTIMIZED_COMPATIBLE_MKV")
        return True

    with patch.object(task, "_run_ffmpeg", side_effect=fake_ffmpeg):
        result = await task.run({"cache_key": "abc123hash:1"})

    assert result is True
    assert media_file.read_bytes() == b"OPTIMIZED_COMPATIBLE_MKV"
    assert mgr.ready_sizes["abc123hash:1"] == len(b"OPTIMIZED_COMPATIBLE_MKV")
    assert "-map" in executed_cmd
    assert executed_cmd[executed_cmd.index("-map") + 1] == "0"
    assert "-c" in executed_cmd
    assert executed_cmd[executed_cmd.index("-c") + 1] == "copy"
    assert "-cues_to_front" in executed_cmd
    assert executed_cmd[executed_cmd.index("-cues_to_front") + 1] == "true"
    assert "-f" in executed_cmd
    assert executed_cmd[executed_cmd.index("-f") + 1] == "matroska"


@pytest.mark.asyncio
async def test_compatible_optimization_audio_fallback(tmp_path):
    media_file = tmp_path / "1.media"
    media_file.write_bytes(b"SOURCE_CONTENT")
    mgr = FakeCacheManager(media_file, status="optimizing")
    logger_factory = FakeLoggerFactory()
    task = OptimizeMediaTask(mgr, logger_factory, optimize_media_target=OptimizeMediaTargetEnum.COMPATIBLE)

    calls = []

    async def fake_ffmpeg(cmd):
        calls.append(list(cmd))
        if len(calls) == 1:
            return False  # Fast copy fails
        out_file = Path(cmd[-1])
        out_file.write_bytes(b"AUDIO_TRANSCODED_MKV")
        return True

    with patch.object(task, "_run_ffmpeg", side_effect=fake_ffmpeg):
        result = await task.run({"cache_key": "abc123hash:1"})

    assert result is True
    assert len(calls) == 2
    assert "-c:a" in calls[1]
    assert calls[1][calls[1].index("-c:a") + 1] == "aac"
    assert "-c:v" in calls[1]
    assert calls[1][calls[1].index("-c:v") + 1] == "copy"
    assert "-cues_to_front" in calls[1]
    assert media_file.read_bytes() == b"AUDIO_TRANSCODED_MKV"


@pytest.mark.asyncio
async def test_compatible_optimization_full_fallback(tmp_path):
    media_file = tmp_path / "1.media"
    media_file.write_bytes(b"SOURCE_CONTENT")
    mgr = FakeCacheManager(media_file, status="optimizing")
    logger_factory = FakeLoggerFactory()
    task = OptimizeMediaTask(mgr, logger_factory, optimize_media_target=OptimizeMediaTargetEnum.COMPATIBLE)

    calls = []

    async def fake_ffmpeg(cmd):
        calls.append(list(cmd))
        if len(calls) < 3:
            return False  # Fast copy and audio fallback fail
        out_file = Path(cmd[-1])
        out_file.write_bytes(b"FULL_TRANSCODED_MKV")
        return True

    with patch.object(task, "_run_ffmpeg", side_effect=fake_ffmpeg):
        result = await task.run({"cache_key": "abc123hash:1"})

    assert result is True
    assert len(calls) == 3
    assert "-c:v" in calls[2]
    assert calls[2][calls[2].index("-c:v") + 1] == "libx264"
    assert media_file.read_bytes() == b"FULL_TRANSCODED_MKV"


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

    with patch("stremio_http_proxy.task.optimize_media_task.detect_media_type", return_value=("video/x-msvideo", "avi")), \
         patch.object(task, "_probe_media", return_value=None), \
         patch.object(task, "_run_ffmpeg", return_value=False):
        result = await task.run({"cache_key": "abc123hash:1"})

    assert result is False
    assert media_file.read_bytes() == original_content
    assert mgr.ready_sizes["abc123hash:1"] == len(original_content)
