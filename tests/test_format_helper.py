from stremio_http_proxy.helper.format_helper import format_bytes


def test_format_bytes_none_or_zero():
    assert format_bytes(None) == "N/A"
    assert format_bytes(0) == "N/A"
    assert format_bytes(-10) == "N/A"


def test_format_bytes_units():
    assert format_bytes(500) == "500.00 B"
    assert format_bytes(1024) == "1.00 KB"
    assert format_bytes(1024 * 1024 * 50) == "50.00 MB"
    assert format_bytes(int(1024 * 1024 * 1024 * 2.45)) == "2.45 GB"
