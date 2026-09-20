import asyncio
import os
import re
from typing import Any
import urllib.parse

import httpx
from fastapi import APIRouter
from fastapi.responses import FileResponse, RedirectResponse, Response
from injector import inject

from stremio_http_proxy.client.torrserver_client import TorrServerClient
from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.manager.hls_chunk_manager import HlsChunkManager
from stremio_http_proxy.service.cache_service import CacheService
from stremio_http_proxy.helper.hash_helper import extract_infohash
from stremio_http_proxy.repository.playback_history_repository import PlaybackHistoryRepository
from stremio_http_proxy.service.download_queue_service import DownloadQueueService
from stremio_http_proxy.service.media_metadata_service import MediaMetadataService
from stremio_http_proxy.service.next_episode_prefetch_service import NextEpisodePrefetchService



class PlaybackController:
    @inject
    def __init__(
        self,
        torrserver_client: TorrServerClient,
        cache_service: CacheService,
        download_queue_service: DownloadQueueService,
        next_episode_prefetch_service: NextEpisodePrefetchService,
        logger_factory: LoggerFactory,
        hls_chunk_manager: HlsChunkManager | None = None,
        http_streams_proxy_enabled: bool = True,
        playback_history_repository: PlaybackHistoryRepository | None = None,
        media_metadata_service: MediaMetadataService | None = None,
    ):
        self.logger = logger_factory.get_logger("stremio_http_proxy.api", "api.log")
        self.torrserver_client = torrserver_client
        self.cache_service = cache_service
        self.download_queue_service = download_queue_service
        self.next_episode_prefetch_service = next_episode_prefetch_service
        self.playback_history_repository = playback_history_repository
        self.media_metadata_service = media_metadata_service
        self.http_streams_proxy_enabled = http_streams_proxy_enabled

        if hls_chunk_manager is not None:
            self.hls_chunk_manager = hls_chunk_manager
        elif hasattr(cache_service, "cache_manager") and hasattr(cache_service.cache_manager, "base_dir"):
            self.hls_chunk_manager = HlsChunkManager(cache_service.cache_manager.base_dir, logger_factory)
        else:
            self.hls_chunk_manager = None
        self._in_flight_requests: set[tuple[str, int | None]] = set()
        self.router = APIRouter(tags=["Playback"])
        self.router.add_api_route("/play", self.play, methods=["GET", "HEAD"])
        self.router.add_api_route("/play/manifest.m3u8", self.play_manifest, methods=["GET", "HEAD"])
        self.router.add_api_route("/play/variant.m3u8", self.play_variant, methods=["GET", "HEAD"])
        self.router.add_api_route("/play/chunk", self.play_chunk, methods=["GET", "HEAD"])
        self.router.add_api_route("/chunk", self.play_chunk, methods=["GET", "HEAD"])

    async def play_manifest(
        self,
        link: str,
        title: str | None = None,
        poster: str | None = None,
        category: str | None = None,
        index: int | None = None,
        content_type: str | None = None,
        content_id: str | None = None,
    ) -> Response:
        self._record_playback(link, title, poster, category, index, content_type, content_id)
        cached_route = self._get_cached_route(link, index, content_id=content_id)

        if cached_route is not None:
            self._schedule_prefetch(content_type, content_id, category)
            return RedirectResponse(url=cached_route, status_code=307)

        if link.startswith(("http://", "https://")):
            cache_key = None
            if hasattr(self.cache_service, "cache_manager"):
                cache_key = self.cache_service.cache_manager.build_cache_key(link, index)

            cleaned, error = await self._verify_and_prepare_manifest(link, cache_key)
            if error is not None:
                self.logger.warning("Stream verification failed on play for %s: %s", link, error)
                if (
                    cache_key
                    and hasattr(self.cache_service, "cache_manager")
                    and hasattr(self.cache_service.cache_manager, "mark_failed")
                ):
                    self.cache_service.cache_manager.mark_failed(cache_key, error, attempt=1)
                return Response(content=f"Stream unreachable: {error}", status_code=502, media_type="text/plain")

            self._schedule_prefetch(content_type, content_id, category)
            self._schedule_downloads(link, title, poster, category, index, content_type, content_id)

            if cleaned is not None:
                return Response(
                    content=cleaned,
                    media_type="application/vnd.apple.mpegurl",
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Cache-Control": "no-cache, no-store, must-revalidate",
                    },
                )
            return RedirectResponse(url=link, status_code=307)

        return await self.play(link, title, poster, category, index, content_type, content_id)

    async def _verify_and_prepare_manifest(
        self, link: str, cache_key: str | None = None
    ) -> tuple[str | None, str | None]:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                resp = await client.get(link)
                if resp.status_code != 200:
                    self.logger.warning(f"Failed to fetch manifest from {link}: status {resp.status_code}")
                    return None, f"Upstream manifest returned HTTP {resp.status_code}"
                manifest_content = resp.text
                base_url = str(resp.url)
        except Exception as e:
            self.logger.exception(f"Exception fetching manifest from {link}")
            return None, f"Exception fetching manifest: {e}"

        lines = manifest_content.splitlines()
        is_master = any(l.strip().startswith("#EXT-X-STREAM-INF") for l in lines)

        first_chunk_url = None

        if is_master:
            expect_variant = False
            first_variant_url = None
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#EXT-X-STREAM-INF"):
                    expect_variant = True
                    continue
                if expect_variant and not stripped.startswith("#") and stripped:
                    abs_variant = urllib.parse.urljoin(base_url, stripped)
                    if abs_variant.startswith("http://") and base_url.startswith("https://"):
                        abs_variant = "https://" + abs_variant[7:]
                    first_variant_url = abs_variant
                    break

            if first_variant_url:
                try:
                    async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                        v_resp = await client.get(first_variant_url)
                        if v_resp.status_code != 200:
                            self.logger.warning(
                                "Failed to fetch variant playlist from %s: status %s",
                                first_variant_url,
                                v_resp.status_code,
                            )
                            return None, f"Upstream variant returned HTTP {v_resp.status_code}"
                        var_lines = v_resp.text.splitlines()
                        var_base = str(v_resp.url)
                        expect_c = False
                        for vl in var_lines:
                            v_str = vl.strip()
                            if v_str.startswith("#EXTINF"):
                                expect_c = True
                                continue
                            if expect_c and not v_str.startswith("#") and v_str:
                                c_url = urllib.parse.urljoin(var_base, v_str)
                                if c_url.startswith("http://") and var_base.startswith("https://"):
                                    c_url = "https://" + c_url[7:]
                                first_chunk_url = c_url
                                break
                except Exception as e:
                    self.logger.warning("Exception fetching variant playlist from %s: %s", first_variant_url, e)
                    return None, f"Failed to fetch variant playlist: {e}"
        else:
            expect_c = False
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("#EXTINF"):
                    expect_c = True
                    continue
                if expect_c and not stripped.startswith("#") and stripped:
                    c_url = urllib.parse.urljoin(base_url, stripped)
                    if c_url.startswith("http://") and base_url.startswith("https://"):
                        c_url = "https://" + c_url[7:]
                    first_chunk_url = c_url
                    break

        if first_chunk_url:
            if cache_key and self.hls_chunk_manager is not None:
                if not self.hls_chunk_manager.has_chunk(cache_key, 0):
                    try:
                        await self.hls_chunk_manager.get_or_download_chunk(
                            cache_key,
                            0,
                            first_chunk_url,
                            timeout=5.0,
                        )
                    except httpx.HTTPStatusError as e:
                        self.logger.warning(
                            "Probe chunk 0 failed for %s: HTTP %s",
                            cache_key,
                            e.response.status_code,
                        )
                        return None, f"Upstream chunk returned HTTP {e.response.status_code}"
                    except Exception as e:
                        self.logger.warning("Probe chunk 0 failed for %s: %s", cache_key, e)
                        return None, f"Upstream chunk probe failed: {e}"
            else:
                try:
                    async with httpx.AsyncClient(follow_redirects=True, timeout=5.0) as client:
                        c_resp = await client.get(first_chunk_url, headers={"Range": "bytes=0-1024"})
                        if c_resp.status_code in (401, 403, 404, 410, 502):
                            self.logger.warning(
                                "Probe chunk 0 returned HTTP %s for %s",
                                c_resp.status_code,
                                first_chunk_url,
                            )
                            return None, f"Upstream chunk returned HTTP {c_resp.status_code}"
                except Exception as e:
                    self.logger.warning("Probe chunk 0 failed for %s: %s", first_chunk_url, e)
                    return None, f"Upstream chunk probe failed: {e}"

        public_base_url = getattr(self.cache_service, "public_base_url", None)
        cleaned = self._clean_hls_manifest(
            manifest_content,
            base_url,
            cache_key=cache_key,
            public_base_url=public_base_url,
            chunk_manager=self.hls_chunk_manager,
        )
        return cleaned, None

    @staticmethod
    def _clean_hls_manifest(
        content: str,
        base_url: str,
        cache_key: str | None = None,
        public_base_url: str | None = None,
        chunk_manager: HlsChunkManager | None = None,
    ) -> str:
        lines = content.splitlines()
        clean_lines = []
        is_master = any(l.strip().startswith("#EXT-X-STREAM-INF") for l in lines)

        if is_master:
            expect_variant_uri = False
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                if "TYPE=SUBTITLES" in stripped:
                    continue
                if stripped.startswith("#EXT-X-STREAM-INF"):
                    stripped = re.sub(r',?SUBTITLES="[^"]*"', "", stripped)
                    expect_variant_uri = True
                    clean_lines.append(stripped)
                    continue
                if expect_variant_uri and not stripped.startswith("#"):
                    abs_uri = urllib.parse.urljoin(base_url, stripped)
                    if abs_uri.startswith("http://") and base_url.startswith("https://"):
                        abs_uri = "https://" + abs_uri[7:]
                    if cache_key and public_base_url:
                        params = urllib.parse.urlencode({"key": cache_key, "link": abs_uri})
                        abs_uri = f"{public_base_url}/play/variant.m3u8?{params}"
                    clean_lines.append(abs_uri)
                    expect_variant_uri = False
                    continue
                if not stripped.startswith("#"):
                    abs_uri = urllib.parse.urljoin(base_url, stripped)
                    if abs_uri.startswith("http://") and base_url.startswith("https://"):
                        abs_uri = "https://" + abs_uri[7:]
                    clean_lines.append(abs_uri)
                elif 'URI="' in stripped:
                    def fix_uri(match: re.Match) -> str:
                        uri = match.group(1)
                        abs_uri = urllib.parse.urljoin(base_url, uri)
                        if abs_uri.startswith("http://") and base_url.startswith("https://"):
                            abs_uri = "https://" + abs_uri[7:]
                        return f'URI="{abs_uri}"'
                    stripped = re.sub(r'URI="([^"]+)"', fix_uri, stripped)
                    clean_lines.append(stripped)
                else:
                    clean_lines.append(stripped)
            return "\n".join(clean_lines) + "\n"

        # Media Playlist (single stream with #EXTINF)
        expect_chunk = False
        chunk_urls: list[str] = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#EXTINF"):
                expect_chunk = True
                clean_lines.append(stripped)
                continue
            if expect_chunk and not stripped.startswith("#"):
                abs_url = urllib.parse.urljoin(base_url, stripped)
                if abs_url.startswith("http://") and base_url.startswith("https://"):
                    abs_url = "https://" + abs_url[7:]
                if cache_key and public_base_url:
                    seq = len(chunk_urls)
                    chunk_urls.append(abs_url)
                    params = urllib.parse.urlencode({"key": cache_key, "seq": str(seq), "url": abs_url})
                    abs_url = f"{public_base_url}/play/chunk?{params}"
                clean_lines.append(abs_url)
                expect_chunk = False
                continue
            clean_lines.append(stripped)

        if cache_key and chunk_urls and chunk_manager:
            chunk_manager.save_playlist_metadata(cache_key, chunk_urls)

        return "\n".join(clean_lines) + "\n"

    async def play_variant(self, key: str, link: str) -> Response:
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
                resp = await client.get(link)
                if resp.status_code != 200:
                    self.logger.warning(f"Failed to fetch variant playlist from {link}: {resp.status_code}")
                    return RedirectResponse(url=link, status_code=307)
                content = resp.text
                base_url = str(resp.url)
        except Exception as e:
            self.logger.warning(f"Error fetching variant playlist from {link}: {e}")
            return RedirectResponse(url=link, status_code=307)

        lines = content.splitlines()
        clean_lines = []
        chunk_urls: list[str] = []
        expect_chunk = False
        public_base_url = getattr(self.cache_service, "public_base_url", "")

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            if stripped.startswith("#EXTINF"):
                expect_chunk = True
                clean_lines.append(stripped)
                continue
            if expect_chunk and not stripped.startswith("#"):
                abs_url = urllib.parse.urljoin(base_url, stripped)
                if abs_url.startswith("http://") and base_url.startswith("https://"):
                    abs_url = "https://" + abs_url[7:]
                seq = len(chunk_urls)
                chunk_urls.append(abs_url)
                params = urllib.parse.urlencode({"key": key, "seq": str(seq), "url": abs_url})
                chunk_route = f"{public_base_url}/play/chunk?{params}"
                clean_lines.append(chunk_route)
                expect_chunk = False
                continue
            clean_lines.append(stripped)

        if chunk_urls and self.hls_chunk_manager:
            self.hls_chunk_manager.save_playlist_metadata(key, chunk_urls)

        rewritten = "\n".join(clean_lines) + "\n"
        return Response(
            content=rewritten,
            media_type="application/vnd.apple.mpegurl",
            headers={
                "Access-Control-Allow-Origin": "*",
                "Cache-Control": "no-cache, no-store, must-revalidate",
            },
        )

    async def play_chunk(self, key: str, seq: int, url: str) -> Response:
        if self.hls_chunk_manager is not None:
            try:
                chunk_path = await self.hls_chunk_manager.get_or_download_chunk(key, seq, url)
                return FileResponse(
                    path=str(chunk_path),
                    media_type="video/mp2t",
                    headers={
                        "Access-Control-Allow-Origin": "*",
                        "Cache-Control": "public, max-age=86400",
                    },
                )
            except httpx.HTTPStatusError as e:
                self.logger.warning(
                    f"Chunk seq={seq} key={key} failed with upstream HTTP {e.response.status_code}"
                )
                if e.response.status_code in (401, 403, 404, 410, 502):
                    return Response(
                        content=f"Chunk error: HTTP {e.response.status_code}",
                        status_code=502,
                        media_type="text/plain",
                    )
                return RedirectResponse(url=url, status_code=307)
            except Exception as e:
                self.logger.warning(f"Failed to get/download chunk seq={seq} key={key}: {e}, redirecting to upstream")
                return RedirectResponse(url=url, status_code=307)
        return RedirectResponse(url=url, status_code=307)

    async def play(
        self,
        link: str,
        title: str | None = None,
        poster: str | None = None,
        category: str | None = None,
        index: int | None = None,
        content_type: str | None = None,
        content_id: str | None = None,
    ) -> RedirectResponse:
        self._record_playback(link, title, poster, category, index, content_type, content_id)
        cached_route = self._get_cached_route(link, index, content_id=content_id)
        if cached_route is not None:
            self._schedule_prefetch(content_type, content_id, category)
            return RedirectResponse(url=cached_route, status_code=307)

        # Non-torrent direct HTTP / HLS streams
        if link.startswith(("http://", "https://")):
            self._schedule_prefetch(content_type, content_id, category)
            self._schedule_downloads(link, title, poster, category, index, content_type, content_id)
            return RedirectResponse(url=link, status_code=307)

        if hasattr(self.torrserver_client, "resolve_file_index"):
            index = await self.torrserver_client.resolve_file_index(
                link,
                index=index,
                content_id=content_id,
                content_type=content_type,
                title=title,
                poster=poster,
                category=category,
            )
        elif index is None or index <= 0:
            index = 1

        self._schedule_prefetch(content_type, content_id, category)
        self._schedule_initialization(link, title, poster, category, index)
        self._schedule_downloads(link, title, poster, category, index, content_type, content_id)

        return RedirectResponse(
            url=self.torrserver_client.build_play_url(link, title, poster, category, index),
            status_code=307,
        )

    def _record_playback(
        self,
        link: str,
        title: str | None,
        poster: str | None,
        category: str | None,
        index: int | None,
        content_type: str | None,
        content_id: str | None,
    ) -> None:
        if not self.playback_history_repository:
            return
        try:
            infohash = extract_infohash(link)
            media_item_id = content_id
            media_id = content_id.split(":")[0] if ":" in content_id else content_id
            if self.media_metadata_service:
                try:
                    media, item = self.media_metadata_service.ensure_media_and_item(
                        content_id=content_id,
                        content_type=content_type,
                        fallback_title=title,
                        fallback_poster=poster,
                    )
                    media_item_id = item.id
                    media_id = media.id
                    if media.poster:
                        poster = media.poster
                except Exception as ex:
                    self.logger.warning("Error resolving media metadata for playback: %s", ex)

            self.playback_history_repository.record_playback(
                media_item_id=media_item_id,
                media_id=media_id,
                title=title,
                poster=poster,
                category=category,
                source_link=link,
                infohash=infohash,
                file_index=index,
            )
        except Exception as e:
            self.logger.warning("Failed to record playback history: %s", e)


    def _schedule_prefetch(
        self,
        content_type: str | None,
        content_id: str | None,
        category: str | None,
    ) -> None:
        if not content_type or not content_id:
            return
        if hasattr(self.next_episode_prefetch_service, "schedule_prefetch"):
            self.next_episode_prefetch_service.schedule_prefetch(content_type, content_id, category)
        elif hasattr(self.next_episode_prefetch_service, "enqueue_next_episode"):
            asyncio.create_task(self.next_episode_prefetch_service.enqueue_next_episode(content_type, content_id, category))

    def _get_cached_route(self, link: str, index: int | None = None, content_id: str | None = None) -> str | None:
        try:
            return self.cache_service.get_cached_route(link, index, content_id=content_id)
        except TypeError:
            return self.cache_service.get_cached_route(link, index)

    def _schedule_downloads(
        self,
        link: str,
        title: str | None,
        poster: str | None,
        category: str | None,
        index: int | None,
        content_type: str | None,
        content_id: str | None,
    ) -> None:
        asyncio.create_task(
            self._enqueue_downloads_in_background(
                link,
                title,
                poster,
                category,
                index,
                content_type,
                content_id,
            )
        )

    def _schedule_initialization(
        self,
        link: str,
        title: str | None,
        poster: str | None,
        category: str | None,
        index: int | None,
    ) -> None:
        request_key = (link, index)
        if request_key in self._in_flight_requests:
            return

        self._in_flight_requests.add(request_key)
        task = asyncio.create_task(self._initialize_in_background(link, title, poster, category, index))
        task.add_done_callback(lambda _: self._in_flight_requests.discard(request_key))

    async def _initialize_in_background(
        self,
        link: str,
        title: str | None,
        poster: str | None,
        category: str | None,
        index: int | None,
    ) -> None:
        try:
            await self.torrserver_client.add_torrent(link, title, poster, category)
            await self.torrserver_client.preload(link, title, poster, category, index)
        except Exception:
            self.logger.exception("Unable to initialize TorrServer playback")

    async def _enqueue_downloads_in_background(
        self,
        link: str,
        title: str | None,
        poster: str | None,
        category: str | None,
        index: int | None,
        content_type: str | None,
        content_id: str | None,
    ) -> None:
        try:
            should_enqueue = (
                not link.startswith(("http://", "https://"))
                or self.http_streams_proxy_enabled
            )
            if should_enqueue:
                await self.download_queue_service.enqueue_download(
                    link,
                    title,
                    poster,
                    category,
                    index,
                    priority=100,
                    trigger="playback",
                    content_type=content_type,
                    content_id=content_id,
                )
        except Exception:
            self.logger.exception("Unable to enqueue cache download work")
