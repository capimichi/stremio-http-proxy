from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from stremio_http_proxy.container.default_container import DefaultContainer
from stremio_http_proxy.controller.addon_controller import AddonController
from stremio_http_proxy.controller.cache_controller import CacheController
from stremio_http_proxy.controller.dashboard_controller import DashboardController
from stremio_http_proxy.controller.health_controller import HealthController
from stremio_http_proxy.controller.playback_controller import PlaybackController
from stremio_http_proxy.controller.whitelist_controller import WhitelistController


default_container = DefaultContainer.getInstance()
app = FastAPI(
    title=default_container.app_name,
    description="Stremio addon proxy backed by TorrServer",
    version="0.1.0",
)

app.include_router(default_container.get(AddonController).router)
app.include_router(default_container.get(CacheController).router)
app.include_router(default_container.get(PlaybackController).router)
app.include_router(default_container.get(DashboardController).router)
app.include_router(default_container.get(WhitelistController).router)
app.include_router(default_container.get(HealthController).router)
app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
if __name__ == "__main__":
    uvicorn.run(
        "stremio_http_proxy.api:app",
        host=default_container.api_host,
        port=default_container.api_port,
        reload=False,
    )
