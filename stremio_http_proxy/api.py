from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.responses import RedirectResponse
import uvicorn

from stremio_http_proxy.container.default_container import DefaultContainer
from stremio_http_proxy.controller.addon_controller import AddonController
from stremio_http_proxy.controller.cache_controller import CacheController
from stremio_http_proxy.controller.health_controller import HealthController
from stremio_http_proxy.controller.playback_controller import PlaybackController


default_container = DefaultContainer.getInstance()
app = FastAPI(
    title=default_container.app_name,
    description="Stremio addon proxy backed by TorrServer",
    version="0.1.0",
)

app.include_router(default_container.get(AddonController).router)
app.include_router(default_container.get(CacheController).router)
app.include_router(default_container.get(PlaybackController).router)
app.include_router(default_container.get(HealthController).router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")


if __name__ == "__main__":
    uvicorn.run(
        "stremio_http_proxy.api:app",
        host=default_container.api_host,
        port=default_container.api_port,
        reload=False,
    )
