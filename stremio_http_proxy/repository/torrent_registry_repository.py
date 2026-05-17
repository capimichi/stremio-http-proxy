import json
from datetime import datetime, timezone
from pathlib import Path

from injector import inject

from stremio_http_proxy.model.playlist_models import TorrentJob


class TorrentRegistryRepository:
    @inject
    def __init__(self, registry_path: str):
        self.registry_path = Path(registry_path)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.registry_path.exists():
            self.registry_path.write_text("[]", encoding="utf-8")

    def list_jobs(self) -> list[TorrentJob]:
        payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
        return [TorrentJob.model_validate(item) for item in payload]

    def get_by_infohash(self, infohash: str) -> TorrentJob | None:
        return next((job for job in self.list_jobs() if job.infohash == infohash), None)

    def upsert(self, job: TorrentJob) -> TorrentJob:
        jobs = self.list_jobs()
        updated = False
        for index, existing in enumerate(jobs):
            if existing.infohash == job.infohash:
                jobs[index] = job
                updated = True
                break
        if not updated:
            jobs.append(job)
        self._write(jobs)
        return job

    def touch(self, infohash: str) -> TorrentJob | None:
        job = self.get_by_infohash(infohash)
        if job is None:
            return None
        job.last_access_at = datetime.now(timezone.utc).isoformat()
        return self.upsert(job)

    def _write(self, jobs: list[TorrentJob]) -> None:
        payload = [job.model_dump(mode="json") for job in jobs]
        self.registry_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
