from injector import inject
from stremio_http_proxy.task.abstract_task import AbstractTask


class TaskRegistry:
    @inject
    def __init__(self):
        self._tasks: dict[str, AbstractTask] = {}

    def register(self, task: AbstractTask) -> None:
        self._tasks[task.name] = task

    def get(self, name: str) -> AbstractTask | None:
        return self._tasks.get(name)

    def has(self, name: str) -> bool:
        return name in self._tasks

    def all_names(self) -> list[str]:
        return list(self._tasks.keys())
