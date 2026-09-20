import asyncio
import time
from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.manager.db_manager import DbManager
from stremio_http_proxy.service.task_service import TaskService
from stremio_http_proxy.task.abstract_task import AbstractTask
from stremio_http_proxy.task.task_registry import TaskRegistry


class DummyTask(AbstractTask):
    name = "dummy_task"

    def __init__(self, should_succeed=True):
        self.should_succeed = should_succeed
        self.executed_with = []

    async def run(self, arguments: dict) -> bool:
        self.executed_with.append(arguments)
        return self.should_succeed


def build_task_service(tmp_path):
    db_manager = DbManager(str(tmp_path / "test_task.sqlite"))
    registry = TaskRegistry()
    logger_factory = LoggerFactory(str(tmp_path / "logs"))
    service = TaskService(db_manager, registry, logger_factory)
    return service, registry


def test_task_service_enqueue_and_deduplication(tmp_path):
    service, registry = build_task_service(tmp_path)

    # 1. Enqueue task with delay
    task_id1 = service.enqueue_task("fetch_episode", {"content_id": "tt123:1:1"}, delay_seconds=10)
    assert task_id1 is not None

    # 2. Duplicate enqueue with same name and arguments returns same ID
    task_id2 = service.enqueue_task("fetch_episode", {"content_id": "tt123:1:1"}, delay_seconds=10)
    assert task_id2 == task_id1

    # 3. Different arguments enqueues new task
    task_id3 = service.enqueue_task("fetch_episode", {"content_id": "tt123:1:2"}, delay_seconds=0)
    assert task_id3 is not None
    assert task_id3 != task_id1


def test_task_service_claim_atomic_and_expired_requeue(tmp_path):
    service, registry = build_task_service(tmp_path)

    # Enqueue task ready now
    task_id = service.enqueue_task("test_task", {"foo": "bar"}, delay_seconds=0)

    # Claim task
    job = asyncio.run(service.claim_next_task("worker-1", lease_seconds=10))
    assert job is not None
    assert job.id == task_id
    assert job.name == "test_task"
    assert job.arguments == {"foo": "bar"}
    assert job.status == "processing"
    assert job.claimed_by == "worker-1"
    assert job.attempt == 1

    # Second claim returns None (no pending tasks ready)
    second_claim = asyncio.run(service.claim_next_task("worker-2"))
    assert second_claim is None


def test_task_service_process_next_task_success(tmp_path):
    service, registry = build_task_service(tmp_path)
    dummy = DummyTask(should_succeed=True)
    registry.register(dummy)

    task_id = service.enqueue_task("dummy_task", {"content_id": "tt3749900:1:2"}, delay_seconds=0)

    # Process task
    processed = asyncio.run(service.process_next_task("worker-1"))
    assert processed is True
    assert dummy.executed_with == [{"content_id": "tt3749900:1:2"}]

    # Claiming again returns None because it is completed
    assert asyncio.run(service.claim_next_task("worker-1")) is None


def test_task_service_process_next_task_retry_and_fail(tmp_path):
    service, registry = build_task_service(tmp_path)
    failing = DummyTask(should_succeed=False)
    registry.register(failing)

    task_id = service.enqueue_task("dummy_task", {"key": "val"}, delay_seconds=0, max_attempts=2)

    # First attempt: returns False -> retried
    processed1 = asyncio.run(service.process_next_task("worker-1"))
    assert processed1 is True

    # Manually reset scheduled_at to test second attempt immediately
    with service.db_manager.session() as session:
        from stremio_http_proxy.entity.task_entry import TaskEntry
        rec = session.get(TaskEntry, task_id)
        assert rec.status == "pending"
        assert rec.attempt == 1
        rec.scheduled_at = time.time() - 1

    # Second attempt: fails permanently because attempt (2) >= max_attempts (2)
    processed2 = asyncio.run(service.process_next_task("worker-1"))
    assert processed2 is True

    with service.db_manager.session() as session:
        from stremio_http_proxy.entity.task_entry import TaskEntry
        rec = session.get(TaskEntry, task_id)
        assert rec.status == "failed"
        assert rec.attempt == 2


def test_task_service_list_tasks(tmp_path):
    service, registry = build_task_service(tmp_path)
    service.enqueue_task("task_a", {"foo": "1"}, delay_seconds=0)
    service.enqueue_task("task_b", {"foo": "2"}, delay_seconds=10)

    tasks = service.list_tasks()
    assert len(tasks) == 2
    assert {t["name"] for t in tasks} == {"task_a", "task_b"}

    pending_tasks = service.list_tasks(status="pending")
    assert len(pending_tasks) == 2

