import asyncio
import json
from pathlib import Path
import pytest
import respx
import httpx

from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.manager.hls_chunk_manager import HlsChunkManager


@pytest.fixture
def chunk_manager(tmp_path):
    logger_factory = LoggerFactory(str(tmp_path / "logs"))
    return HlsChunkManager(tmp_path / "cache", logger_factory)


def test_chunk_paths_and_metadata(chunk_manager):
    cache_key = "test_infohash:0"
    
    assert not chunk_manager.has_chunk(cache_key, 0)
    assert chunk_manager.get_playlist_metadata(cache_key) is None

    # Test saving metadata
    urls = [
        "https://mediaflow.example.com/seg0.ts",
        "https://mediaflow.example.com/seg1.ts",
    ]
    chunk_manager.save_playlist_metadata(cache_key, urls)
    assert chunk_manager.get_playlist_metadata(cache_key) == urls

    # Check chunks directory was created
    chunks_dir = chunk_manager.get_chunks_dir(cache_key)
    assert chunks_dir.is_dir()
    assert (chunks_dir / "playlist.json").is_file()


@pytest.mark.asyncio
async def test_get_or_download_chunk(chunk_manager):
    cache_key = "stream_hash:1"
    chunk_url = "https://mediaflow.example.com/stream/segment001.ts"
    chunk_content = b"TS_PACKET_DATA_12345"

    with respx.mock:
        respx.get(chunk_url).respond(
            status_code=200,
            content=chunk_content,
            headers={"content-type": "video/mp2t"},
        )

        # First call: downloads the chunk
        path = await chunk_manager.get_or_download_chunk(cache_key, 1, chunk_url)
        assert path.is_file()
        assert path.read_bytes() == chunk_content
        assert chunk_manager.has_chunk(cache_key, 1)
        assert chunk_manager.get_downloaded_indices(cache_key) == {1}
        assert chunk_manager.get_chunks_total_bytes(cache_key) == len(chunk_content)

        # Second call: returns cached file without calling upstream again
        path2 = await chunk_manager.get_or_download_chunk(cache_key, 1, chunk_url)
        assert path2 == path
        assert len(respx.calls) == 1


@pytest.mark.asyncio
async def test_merge_chunks_to_media(chunk_manager, monkeypatch, tmp_path):
    cache_key = "merge_test:0"
    chunks_dir = chunk_manager.get_chunks_dir(cache_key)

    # Write 3 dummy chunks
    for i in range(3):
        (chunks_dir / f"{i:05d}.ts").write_bytes(b"DATA" * 10)

    output_path = tmp_path / "cache" / "merge_test" / "0.media"

    class FakeProc:
        def __init__(self, target_file):
            self.returncode = 0
            self.target_file = target_file

        async def communicate(self):
            self.target_file.parent.mkdir(parents=True, exist_ok=True)
            self.target_file.write_bytes(b"FINAL_MP4_CONTENT")
            return b"", b""

    async def fake_subprocess_exec(*cmd, **kwargs):
        output_file = Path(cmd[-1])
        return FakeProc(output_file)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess_exec)

    success = await chunk_manager.merge_chunks_to_media(cache_key, 3, output_path)
    assert success is True
    assert output_path.is_file()
    assert output_path.read_bytes() == b"FINAL_MP4_CONTENT"

    # Concat file should have been written with relative paths
    concat_file = chunks_dir / "concat_list.txt"
    assert concat_file.is_file()
    content = concat_file.read_text()
    assert "file '00000.ts'" in content
    assert "file '00001.ts'" in content
    assert "file '00002.ts'" in content

    # Test cleanup
    chunk_manager.cleanup_chunks(cache_key)
    assert not chunks_dir.exists()
