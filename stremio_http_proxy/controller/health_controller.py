from fastapi import APIRouter
from fastapi.responses import FileResponse


class HealthController:
    def __init__(self):
        self.router = APIRouter(tags=["Health"])
        self.router.add_api_route("/health", self.health_check, methods=["GET"])
        self.router.add_api_route("/favicon.ico", self.favicon, methods=["GET"], include_in_schema=False)

    async def health_check(self) -> dict:
        return {"status": "ok"}

    async def favicon(self) -> FileResponse:
        return FileResponse("static/favicon.ico")
