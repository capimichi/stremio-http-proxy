from pathlib import Path
import filetype


def detect_media_type(file_path: str | Path) -> tuple[str, str]:
    """Detects MIME type and file extension for media streaming.

    Reads only the initial header bytes of the file.
    Returns a tuple of (media_type, extension).
    Defaults to ('video/mp4', 'mp4') if undetected.
    """
    try:
        kind = filetype.guess(file_path)
        if kind is not None and kind.mime:
            return kind.mime, kind.extension
    except Exception:
        pass

    # Custom check for MPEG-TS streams (sync byte 0x47)
    try:
        with open(file_path, "rb") as f:
            header = f.read(188)
            if header and header[0] == 0x47:
                return "video/mp2t", "ts"
    except Exception:
        pass

    return "video/mp4", "mp4"
