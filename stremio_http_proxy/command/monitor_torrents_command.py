import click
from injector import inject

from stremio_http_proxy.command.abstract_command import AbstractCommand
from stremio_http_proxy.service.torrent_service import TorrentService


class MonitorTorrentsCommand(AbstractCommand):
    command_name = "monitor-torrents"

    @inject
    def __init__(self, torrent_service: TorrentService):
        self.torrent_service = torrent_service

    def run(self):
        jobs = self.torrent_service.list_jobs()
        if not jobs:
            click.echo("No torrents registered")
            return
        for job in jobs:
            click.echo(
                f"{job.infohash} status={job.status} segments={len(job.segments)} storage={job.storage_path or '-'}"
            )
