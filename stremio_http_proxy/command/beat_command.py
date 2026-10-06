import click
from injector import inject

from stremio_http_proxy.command.abstract_command import AbstractCommand


class BeatCommand(AbstractCommand):
    """Command to start the Celery Beat periodic task scheduler."""

    command_name = "beat"

    @inject
    def __init__(self):
        pass

    def register_options(self, fn):
        fn = click.option(
            "--loglevel",
            "-l",
            default="info",
            show_default=True,
            help="Logging level for Celery Beat.",
        )(fn)
        return fn

    def run(self, loglevel: str = "info"):
        from stremio_http_proxy.beat import celery_app

        click.echo("Starting Celery Beat scheduler...")
        celery_app.Beat(loglevel=loglevel).run()
