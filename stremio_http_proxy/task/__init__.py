from stremio_http_proxy.task.abstract_task import AbstractTask
from stremio_http_proxy.task.fetch_media_task import FetchMediaTask
from stremio_http_proxy.task.fetch_next_episode_task import FetchNextEpisodeTask
from stremio_http_proxy.task.optimize_media_task import OptimizeMediaTask
from stremio_http_proxy.task.task_registry import TaskRegistry

__all__ = [
    "AbstractTask",
    "FetchMediaTask",
    "FetchNextEpisodeTask",
    "OptimizeMediaTask",
    "TaskRegistry",
]

