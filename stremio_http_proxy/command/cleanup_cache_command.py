import click
from injector import inject

from stremio_http_proxy.command.abstract_command import AbstractCommand
from stremio_http_proxy.service.torrent_service import TorrentService


class CleanupCacheCommand(AbstractCommand):
    command_name = "cleanup-cache"

    @inject
    def __init__(self, torrent_service: TorrentService, default_cache_max_age_days: int):
        self.torrent_service = torrent_service
        self.default_cache_max_age_days = default_cache_max_age_days

    def register_options(self, fn):
        fn = click.option(
            "--max-size-gb",
            default=None,
            type=int,
            help="Optional cache size limit override.",
        )(fn)
        fn = click.option(
            "--older-than-days",
            default=self.default_cache_max_age_days,
            type=int,
            show_default=True,
            help="Delete cached segments older than this age.",
        )(fn)
        return fn

    def run(self, older_than_days: int, max_size_gb: int | None):
        summary = self.torrent_service.cleanup(older_than_days, max_size_gb)
        click.echo(
            f"Deleted {summary['deleted_files']} files, reclaimed {summary['reclaimed_bytes']} bytes"
        )
