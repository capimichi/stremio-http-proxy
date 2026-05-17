import click

from stremio_http_proxy.command.add_torrent_command import AddTorrentCommand
from stremio_http_proxy.command.cleanup_cache_command import CleanupCacheCommand
from stremio_http_proxy.command.monitor_torrents_command import MonitorTorrentsCommand
from stremio_http_proxy.command.serve_command import ServeCommand
from stremio_http_proxy.container.default_container import DefaultContainer


@click.group()
def cli():
    pass


default_container = DefaultContainer.getInstance()
cli.add_command(default_container.get(ServeCommand).to_click_command())
cli.add_command(default_container.get(AddTorrentCommand).to_click_command())
cli.add_command(default_container.get(MonitorTorrentsCommand).to_click_command())
cli.add_command(default_container.get(CleanupCacheCommand).to_click_command())


if __name__ == "__main__":
    cli()
