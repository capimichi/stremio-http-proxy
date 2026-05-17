from abc import ABC, abstractmethod

import click


class AbstractCommand(ABC):
    command_name = "command"

    def register_options(self, fn):
        return fn

    @abstractmethod
    def run(self, **kwargs):
        pass

    def to_click_command(self) -> click.Command:
        @click.command(name=self.command_name)
        @self.register_options
        def command(**kwargs):
            self.run(**kwargs)

        return command
