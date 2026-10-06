import logging
import os
import sys

from celery import Celery
from celery.signals import after_setup_logger, after_setup_task_logger

app_name = os.environ.get("APP_NAME", "stremio-http-proxy")
redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
celery_broker_url = os.environ.get("CELERY_BROKER_URL", redis_url)
celery_result_backend = os.environ.get("CELERY_RESULT_BACKEND", redis_url)
timezone = os.environ.get("TIMEZONE", "Europe/Rome")

celery_app = Celery(
    app_name,
    broker=celery_broker_url,
    backend=celery_result_backend,
    include=[
        "stremio_http_proxy.task.download_media_task",
        "stremio_http_proxy.task.optimize_media_task",
        "stremio_http_proxy.task.fetch_media_task",
        "stremio_http_proxy.task.fetch_next_episode_task",
        "stremio_http_proxy.task.enrich_media_metadata_task",
        "stremio_http_proxy.task.cleanup_cache_task",
    ],
)

celery_app.conf.update(
    task_default_queue="default",
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone=timezone,
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "stremio_http_proxy.task.download_media_task": {"queue": "downloads"},
        "stremio_http_proxy.task.optimize_media_task": {"queue": "transcode"},
        "stremio_http_proxy.task.fetch_media_task": {"queue": "default"},
        "stremio_http_proxy.task.fetch_next_episode_task": {"queue": "default"},
        "stremio_http_proxy.task.enrich_media_metadata_task": {"queue": "default"},
        "stremio_http_proxy.task.cleanup_cache_task": {"queue": "default"},
    },
)


@after_setup_logger.connect
@after_setup_task_logger.connect
def setup_celery_file_logging(logger=None, **kwargs):
    if logger is None:
        return
    log_dir = os.environ.get("LOG_DIR", "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_path = os.path.abspath(os.path.join(log_dir, "celery.log"))
    has_file = any(
        isinstance(h, logging.FileHandler) and getattr(h, "baseFilename", None) == log_path
        for h in logger.handlers
    )
    if not has_file:
        fh = logging.FileHandler(log_path, mode="a")
        fh.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(fh)


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] != "worker":
        args = ["worker", *args]
    if not any(arg in args for arg in ("-l", "--loglevel")):
        args.extend(["--loglevel=info"])
    celery_app.worker_main(argv=args)
