import json
import time
from typing import Any
from injector import inject
from sqlalchemy import select, update

from stremio_http_proxy.entity.task_entry import TaskEntry
from stremio_http_proxy.logger.logger_factory import LoggerFactory
from stremio_http_proxy.manager.db_manager import DbManager
from stremio_http_proxy.model.task_job import TaskJob
from stremio_http_proxy.task.task_registry import TaskRegistry


class TaskService:
    @inject
    def __init__(
        self,
        db_manager: DbManager,
        task_registry: TaskRegistry,
        logger_factory: LoggerFactory,
    ):
        self.db_manager = db_manager
        self.task_registry = task_registry
        self.logger = logger_factory.get_logger("stremio_http_proxy.task_service", "task_service.log")

    def enqueue_task(
        self,
        name: str,
        arguments: dict[str, Any],
        delay_seconds: int = 0,
        max_attempts: int = 3,
        deduplicate: bool = True,
    ) -> int | None:
        now = time.time()
        scheduled_at = now + max(0, delay_seconds)
        raw_arguments = json.dumps(arguments, sort_keys=True)

        with self.db_manager.session() as session:
            if deduplicate:
                existing = session.scalars(
                    select(TaskEntry).where(
                        TaskEntry.name == name,
                        TaskEntry.arguments == raw_arguments,
                        TaskEntry.status.in_(["pending", "processing"]),
                    )
                ).first()
                if existing is not None:
                    self.logger.info("Task %s already %s (id=%s), skipping duplicate enqueue", name, existing.status, existing.id)
                    return existing.id

            entry = TaskEntry(
                name=name,
                arguments=raw_arguments,
                status="pending",
                scheduled_at=scheduled_at,
                created_at=now,
                updated_at=now,
                attempt=0,
                max_attempts=max_attempts,
            )
            session.add(entry)
            session.flush()
            task_id = entry.id
            self.logger.info("Enqueued task %s (id=%s) scheduled at %s", name, task_id, scheduled_at)
            return task_id

    async def claim_next_task(self, worker_id: str, lease_seconds: int = 180) -> TaskJob | None:
        now = time.time()
        with self.db_manager.session() as session:
            # 1. Requeue expired processing tasks
            expired_records = session.scalars(
                select(TaskEntry).where(
                    TaskEntry.status == "processing",
                    TaskEntry.processing_expires_at.is_not(None),
                    TaskEntry.processing_expires_at <= now,
                )
            ).all()
            for record in expired_records:
                record.status = "pending"
                record.claimed_by = None
                record.claimed_at = None
                record.processing_expires_at = None
                record.scheduled_at = now
                record.updated_at = now
                self.logger.warning("Requeued expired task %s (id=%s)", record.name, record.id)

            # 2. Find eligible pending candidate tasks
            candidates = session.scalars(
                select(TaskEntry)
                .where(
                    TaskEntry.status == "pending",
                    TaskEntry.scheduled_at <= now,
                )
                .order_by(TaskEntry.scheduled_at.asc())
                .limit(5)
            ).all()

            # 3. Atomically claim one
            for record in candidates:
                claimed = session.execute(
                    update(TaskEntry)
                    .where(
                        TaskEntry.id == record.id,
                        TaskEntry.status == "pending",
                    )
                    .values(
                        status="processing",
                        claimed_at=now,
                        claimed_by=worker_id,
                        processing_expires_at=now + lease_seconds,
                        updated_at=now,
                        attempt=TaskEntry.attempt + 1,
                    )
                )
                if claimed.rowcount != 1:
                    continue

                claimed_record = session.get(TaskEntry, record.id)
                return self._to_job(claimed_record)

        return None

    async def complete_task(self, task_id: int) -> None:
        now = time.time()
        with self.db_manager.session() as session:
            record = session.get(TaskEntry, task_id)
            if record:
                record.status = "completed"
                record.claimed_by = None
                record.claimed_at = None
                record.processing_expires_at = None
                record.updated_at = now
                self.logger.info("Completed task %s (id=%s)", record.name, record.id)

    async def fail_task(
        self,
        task_id: int,
        error: str,
        retry: bool = False,
        retry_delay_seconds: int = 60,
    ) -> None:
        now = time.time()
        with self.db_manager.session() as session:
            record = session.get(TaskEntry, task_id)
            if record:
                record.last_error = error
                record.updated_at = now
                record.claimed_by = None
                record.claimed_at = None
                record.processing_expires_at = None
                if retry:
                    record.status = "pending"
                    record.scheduled_at = now + retry_delay_seconds
                    self.logger.warning("Retrying task %s (id=%s) in %ss: %s", record.name, record.id, retry_delay_seconds, error)
                else:
                    record.status = "failed"
                    self.logger.error("Failed task %s (id=%s) permanently: %s", record.name, record.id, error)

    async def process_next_task(self, worker_id: str) -> bool:
        job = await self.claim_next_task(worker_id)
        if job is None:
            return False

        task_handler = self.task_registry.get(job.name)
        if task_handler is None:
            err = f"No handler registered for task: {job.name}"
            self.logger.error(err)
            await self.fail_task(job.id, error=err, retry=False)
            return True

        self.logger.info("Worker %s executing task %s (id=%s)", worker_id, job.name, job.id)
        try:
            success = await task_handler.run(job.arguments)
            if success:
                await self.complete_task(job.id)
            else:
                can_retry = job.attempt < job.max_attempts
                await self.fail_task(
                    job.id,
                    error="Task execution returned False",
                    retry=can_retry,
                    retry_delay_seconds=60 * job.attempt,
                )
            return True
        except Exception as exc:
            err = str(exc)
            self.logger.exception("Exception executing task %s (id=%s): %s", job.name, job.id, err)
            can_retry = job.attempt < job.max_attempts
            await self.fail_task(
                job.id,
                error=err,
                retry=can_retry,
                retry_delay_seconds=60 * job.attempt,
            )
            return True

    def _to_job(self, record: TaskEntry) -> TaskJob:
        try:
            parsed_args = json.loads(record.arguments) if record.arguments else {}
        except Exception:
            parsed_args = {}

        return TaskJob(
            id=record.id,
            name=record.name,
            arguments=parsed_args,
            status=record.status,
            scheduled_at=record.scheduled_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
            claimed_by=record.claimed_by,
            claimed_at=record.claimed_at,
            processing_expires_at=record.processing_expires_at,
            attempt=record.attempt,
            max_attempts=record.max_attempts,
            last_error=record.last_error,
        )
