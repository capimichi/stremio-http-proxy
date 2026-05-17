import click
from injector import inject

from stremio_http_proxy.command.abstract_command import AbstractCommand
from stremio_http_proxy.service.torrent_service import TorrentService


class AddTorrentCommand(AbstractCommand):
    command_name = "add-torrent"

    @inject
    def __init__(self, torrent_service: TorrentService):
        self.torrent_service = torrent_service

    def register_options(self, fn):
        fn = click.option("--segment", "segments", multiple=True, help="Register one HLS segment name.")(fn)
        fn = click.option("--magnet", required=True, help="Magnet URI to register.")(fn)
        return fn

    def run(self, magnet: str, segments: tuple[str, ...]):
        job = self.torrent_service.add_magnet(magnet, list(segments))
        click.echo(f"Registered torrent {job.infohash} with {len(job.segments)} segments")
