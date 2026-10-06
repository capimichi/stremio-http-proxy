from abc import ABC, abstractmethod
from typing import Any


class AbstractTask(ABC):
    name: str = ""
    task_name: str = ""

    @abstractmethod
    def run(self, *args: Any, **kwargs: Any) -> Any:
        """
        Execute the task.
        """
        raise NotImplementedError


class AbstractPeriodicTask(AbstractTask):
    """Base class for Celery tasks scheduled periodically by Celery Beat."""

    @classmethod
    @abstractmethod
    def get_schedule(cls, container: Any) -> Any:
        """Return the schedule interval (in seconds) or crontab schedule."""
        raise NotImplementedError
