from stremio_http_proxy.command.beat_command import BeatCommand
from stremio_http_proxy.command.worker_command import WorkerCommand
from stremio_http_proxy.worker import celery_app


def test_celery_app_configuration():
    assert celery_app.conf.task_default_queue == "default"
    assert celery_app.conf.task_serializer == "json"
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.worker_prefetch_multiplier == 1

    routes = celery_app.conf.task_routes
    assert routes["stremio_http_proxy.task.download_media_task"]["queue"] == "downloads"
    assert routes["stremio_http_proxy.task.optimize_media_task"]["queue"] == "transcode"
    assert routes["stremio_http_proxy.task.fetch_media_task"]["queue"] == "default"
    assert routes["stremio_http_proxy.task.fetch_next_episode_task"]["queue"] == "default"


def test_worker_and_beat_commands():
    worker_cmd = WorkerCommand()
    assert worker_cmd.command_name == "worker"

    beat_cmd = BeatCommand()
    assert beat_cmd.command_name == "beat"
