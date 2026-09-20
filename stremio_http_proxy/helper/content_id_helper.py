def parse_content_id(
    content_id: str | None, content_type: str | None = None
) -> tuple[str, str, int | None, int | None, str]:
    """
    Parses content_id into:
    (media_id, item_id, season, episode, media_type)
    """
    if not content_id:
        return "", "", None, None, content_type or "movie"

    if ":" in content_id:
        parts = content_id.split(":")
        media_id = parts[0]
        season = None
        episode = None
        if len(parts) >= 3:
            try:
                season = int(parts[1])
                episode = int(parts[2])
            except (ValueError, TypeError):
                pass
        elif len(parts) == 2:
            try:
                episode = int(parts[1])
            except (ValueError, TypeError):
                pass

        if season is not None and episode is not None:
            item_id = f"{media_id}:{season}:{episode}"
        else:
            item_id = content_id
        determined_type = content_type or "series"
        return media_id, item_id, season, episode, determined_type

    determined_type = content_type or "movie"
    return content_id, content_id, None, None, determined_type
