import sys

from stremio_http_proxy.worker import celery_app

celery_app.conf.beat_schedule = {
    "cleanup_cache": {
        "task": "stremio_http_proxy.task.cleanup_cache_task",
        "schedule": 1800.0,
    },
}

if __name__ == "__main__":
    args = sys.argv[1:]
    if not args or args[0] != "beat":
        args = ["beat", *args]
    if not any(arg in args for arg in ("-l", "--loglevel")):
        args.extend(["--loglevel=info"])
    celery_app.start(argv=args)
