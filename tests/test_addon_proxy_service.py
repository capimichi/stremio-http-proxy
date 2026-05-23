import asyncio

from stremio_http_proxy.service.addon_proxy_service import AddonProxyService


class FakeUpstreamClient:
    async def get_json(self, path: str, query_params: dict[str, str] | None = None) -> dict:
        return {"streams": [{"magnet": "magnet:?xt=urn:btih:abc"}], "path": path}


class FakeStreamRewriteService:
    def __init__(self):
        self.calls: list[tuple] = []

    async def rewrite(
        self,
        payload: dict,
        category: str | None = None,
        meta_type: str | None = None,
        meta_id: str | None = None,
        season: int | None = None,
        episode: int | None = None,
    ) -> dict:
        self.calls.append((payload, category, meta_type, meta_id, season, episode))
        return {"rewritten": True, "category": category}


def test_addon_proxy_service_awaits_stream_rewrite_for_stream_paths():
    rewrite_service = FakeStreamRewriteService()
    service = AddonProxyService(FakeUpstreamClient(), rewrite_service)

    result = asyncio.run(service.proxy_json("/stream/movie/tt123.json"))

    assert result == {"rewritten": True, "category": "movie"}
    assert rewrite_service.calls[0][1] == "movie"


def test_addon_proxy_service_skips_rewrite_for_non_stream_paths():
    rewrite_service = FakeStreamRewriteService()
    service = AddonProxyService(FakeUpstreamClient(), rewrite_service)

    result = asyncio.run(service.proxy_json("/manifest.json"))

    assert result["path"] == "/manifest.json"
    assert rewrite_service.calls == []
