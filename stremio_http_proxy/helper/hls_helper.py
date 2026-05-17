def build_segment_uri(base_url: str, infohash: str, segment_name: str) -> str:
    return f"{base_url}/streams/{infohash}/segments/{segment_name}.ts"


def build_playlist(base_url: str, infohash: str, segments: list[str], target_duration: int = 6) -> str:
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{target_duration}",
        "#EXT-X-MEDIA-SEQUENCE:0",
        "#EXT-X-PLAYLIST-TYPE:VOD",
    ]
    for segment in segments:
        lines.append(f"#EXTINF:{target_duration:.3f},")
        lines.append(build_segment_uri(base_url, infohash, segment))
    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"
