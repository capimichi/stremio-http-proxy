import click

from stremio_http_proxy.command.serve_command import ServeCommand
from stremio_http_proxy.container.default_container import DefaultContainer


@click.group()
def cli():
    pass


default_container = DefaultContainer.getInstance()
cli.add_command(default_container.get(ServeCommand).to_click_command())


if __name__ == "__main__":
    cli()
