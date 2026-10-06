import logging
from typing import Any
from celery import shared_task
from injector import inject

from stremio_http_proxy.manager.cache_manager import CacheManager
from stremio_http_proxy.task.abstract_task import AbstractPeriodicTask

logger = logging.getLogger(__name__)


class CleanupCacheTask(AbstractPeriodicTask):
    task_name = "stremio_http_proxy.task.cleanup_cache_task"
    name = "cleanup_cache"

    @inject
    def __init__(self, cache_manager: CacheManager):
        self.cache_manager = cache_manager

    @classmethod
    def get_schedule(cls, container: Any) -> float:
        return 1800.0

    def run(self, *args: Any, **kwargs: Any) -> bool:
        logger.info("Starting CleanupCacheTask")
        try:
            self.cache_manager.prune()
            if hasattr(self.cache_manager, "enforce_cache_limits"):
                self.cache_manager.enforce_cache_limits()
            logger.info("CleanupCacheTask completed successfully")
            return True
        except Exception as exc:
            logger.exception("CleanupCacheTask failed: %s", exc)
            return False


@shared_task(name="stremio_http_proxy.task.cleanup_cache_task", bind=True, max_retries=1)
def cleanup_cache_task(self):
    from stremio_http_proxy.container.default_container import DefaultContainer

    container = DefaultContainer.getInstance()
    try:
        task: CleanupCacheTask = container.get(CleanupCacheTask)
        return task.run()
    except Exception as exc:
        logger.exception("cleanup_cache_task error: %s", exc)
        raise self.retry(exc=exc, countdown=60)
