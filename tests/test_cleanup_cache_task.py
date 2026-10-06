from unittest.mock import MagicMock
from stremio_http_proxy.task.cleanup_cache_task import CleanupCacheTask


def test_cleanup_cache_task_calls_prune_and_enforce_limits():
    cache_manager = MagicMock()
    task = CleanupCacheTask(cache_manager)

    assert task.get_schedule(None) == 1800.0

    res = task.run()
    assert res is True
    cache_manager.prune.assert_called_once()
    cache_manager.enforce_cache_limits.assert_called_once()
