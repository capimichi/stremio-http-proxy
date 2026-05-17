from urllib.parse import parse_qs, urlparse


def normalize_infohash(value: str) -> str:
    return value.lower().strip()


def extract_infohash(value: str | None) -> str | None:
    if not value:
        return None

    text = value.strip()
    if text.startswith("magnet:"):
        parsed = urlparse(text)
        xt_values = parse_qs(parsed.query).get("xt", [])
        for xt_value in xt_values:
            prefix = "urn:btih:"
            if xt_value.startswith(prefix):
                return normalize_infohash(xt_value[len(prefix):])
        return None

    marker = "btih:"
    if marker in text:
        return normalize_infohash(text.split(marker, 1)[1].split("&", 1)[0])

    if len(text) in {40, 32}:
        return normalize_infohash(text)

    return None
