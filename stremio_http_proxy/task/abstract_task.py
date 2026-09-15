from abc import ABC, abstractmethod
from typing import Any


class AbstractTask(ABC):
    name: str

    @abstractmethod
    async def run(self, arguments: dict[str, Any]) -> bool:
        """
        Execute the task.
        Return True if completed successfully, or False / raise Exception if failed.
        """
        raise NotImplementedError
