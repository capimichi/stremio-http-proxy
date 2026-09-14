from stremio_http_proxy.helper.media_type_helper import detect_media_type


def test_detect_media_type_avi(tmp_path):
    f = tmp_path / "test.media"
    f.write_bytes(b"RIFF\x24\x00\x00\x00AVI LIST")
    media_type, ext = detect_media_type(f)
    assert media_type == "video/x-msvideo"
    assert ext == "avi"


def test_detect_media_type_mp4(tmp_path):
    f = tmp_path / "test.media"
    f.write_bytes(b"\x00\x00\x00\x18ftypmp42\x00\x00\x00\x00isommp42")
    media_type, ext = detect_media_type(f)
    assert media_type == "video/mp4"
    assert ext == "mp4"


def test_detect_media_type_mkv(tmp_path):
    f = tmp_path / "test.media"
    f.write_bytes(b"\x1a\x45\xdf\xa3\x93\x42\x82\x88matroska")
    media_type, ext = detect_media_type(f)
    assert media_type == "video/x-matroska"
    assert ext == "mkv"


def test_detect_media_type_ts(tmp_path):
    f = tmp_path / "test.media"
    f.write_bytes(b"\x47\x40\x00\x10" + b"\x00" * 184)
    media_type, ext = detect_media_type(f)
    assert media_type == "video/mp2t"
    assert ext == "ts"


def test_detect_media_type_fallback_on_unknown(tmp_path):
    f = tmp_path / "test.media"
    f.write_bytes(b"some unknown random binary data")
    media_type, ext = detect_media_type(f)
    assert media_type == "video/mp4"
    assert ext == "mp4"


def test_detect_media_type_fallback_on_missing_file(tmp_path):
    missing = tmp_path / "missing.media"
    media_type, ext = detect_media_type(missing)
    assert media_type == "video/mp4"
    assert ext == "mp4"
