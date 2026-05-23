import asyncio

from injector import inject

from stremio_http_proxy.client.torrserver_client import TorrServerClient


class TorrentHealthService:
    @inject
    def __init__(self, torrserver_client: TorrServerClient):
        self.client = torrserver_client

    async def check_batch(self, links: list[str], timeout: float = 15.0) -> dict[str, bool]:
        links_to_check = links[:10]

        async def check_one(link: str) -> tuple[str, bool]:
            try:
                result = await self.client.add_and_get_status(link, timeout=timeout)
                return link, result is not None
            except Exception:
                return link, False

        try:
            async with asyncio.timeout(timeout):
                results = await asyncio.gather(
                    *[check_one(link) for link in links_to_check],
                    return_exceptions=True,
                )
        except TimeoutError:
            return {}

        health_map: dict[str, bool] = {}
        for r in results:
            if isinstance(r, tuple):
                health_map[r[0]] = r[1]
        return health_map
