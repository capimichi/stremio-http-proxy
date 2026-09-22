import hashlib
import os
from pathlib import Path
from urllib.parse import urlparse
import httpx
from injector import inject

from stremio_http_proxy.logger.logger_factory import LoggerFactory


class MediaAssetManager:
    @inject
    def __init__(self, media_dir: str = "var/media", logger_factory: LoggerFactory | None = None):
        self.media_dir = Path(media_dir)
        self.images_dir = self.media_dir / "images"
        self.images_dir.mkdir(parents=True, exist_ok=True)
        if logger_factory:
            self.logger = logger_factory.get_logger("stremio_http_proxy.media_asset", "media_asset.log")
        else:
            self.logger = None

    def get_extension(self, url: str) -> str:
        parsed = urlparse(url)
        path = parsed.path
        ext = os.path.splitext(path)[1].lower()
        if ext in [".jpg", ".jpeg", ".png", ".webp", ".svg"]:
            return ext
        return ".jpg"

    async def save_image_from_url(
        self,
        url: str | None,
        subfolder: str,
        filename_prefix: str,
    ) -> str | None:
        if not url or not url.strip():
            return None
        url = url.strip()
        if url.startswith("/media/"):
            return url

        ext = self.get_extension(url)
        safe_subfolder = self.images_dir / subfolder
        safe_subfolder.mkdir(parents=True, exist_ok=True)

        url_hash = hashlib.md5(url.encode("utf-8")).hexdigest()[:8]
        filename = f"{filename_prefix}_{url_hash}{ext}"
        target_path = safe_subfolder / filename
        static_url = f"/media/images/{subfolder}/{filename}"

        if target_path.exists() and target_path.stat().st_size > 0:
            return static_url

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                resp = await client.get(url)
                if resp.status_code == 200 and resp.content:
                    with target_path.open("wb") as f:
                        f.write(resp.content)
                    return static_url
                else:
                    if self.logger:
                        self.logger.warning("Failed to fetch image %s: status %s", url, resp.status_code)
                    return url
        except Exception as e:
            if self.logger:
                self.logger.warning("Error downloading image %s: %s", url, e)
            return url
