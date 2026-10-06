import click
from injector import inject

from stremio_http_proxy.command.abstract_command import AbstractCommand


class WorkerCommand(AbstractCommand):
    """Command to start the Celery background worker."""

    command_name = "worker"

    @inject
    def __init__(self):
        pass

    def register_options(self, fn):
        fn = click.option(
            "--concurrency",
            "-c",
            default=2,
            type=int,
            show_default=True,
            help="Number of worker processes.",
        )(fn)
        fn = click.option(
            "--queues",
            "-Q",
            default="downloads,transcode,default",
            show_default=True,
            help="Comma-separated list of queues to consume from.",
        )(fn)
        fn = click.option(
            "--loglevel",
            "-l",
            default="info",
            show_default=True,
            help="Logging level for Celery worker.",
        )(fn)
        return fn

    def run(self, concurrency: int = 2, queues: str = "downloads,transcode,default", loglevel: str = "info"):
        from stremio_http_proxy.worker import celery_app

        celery_app.worker_main(
            argv=[
                "worker",
                f"--loglevel={loglevel}",
                f"--concurrency={concurrency}",
                f"--queues={queues}",
            ]
        )
