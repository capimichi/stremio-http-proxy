from fastapi import APIRouter


class HealthController:
    def __init__(self):
        self.router = APIRouter(tags=["Health"])
        self.router.add_api_route("/health", self.health_check, methods=["GET"])

    async def health_check(self) -> dict:
        return {"status": "ok"}
