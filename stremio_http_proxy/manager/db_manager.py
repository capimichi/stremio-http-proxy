from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from stremio_http_proxy.entity.cache_entry import Base
from stremio_http_proxy.entity.prefetch_entry import PrefetchEntry
from stremio_http_proxy.entity.task_entry import TaskEntry


class DbManager:
    def __init__(self, sqlite_path: str):
        self.sqlite_path = Path(sqlite_path)
        self.sqlite_path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(
            f"sqlite:///{self.sqlite_path}",
            connect_args={"check_same_thread": False},
        )
        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self._initialize()

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _initialize(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text("PRAGMA journal_mode=WAL"))
            connection.execute(text("PRAGMA synchronous=NORMAL"))
            connection.execute(text("PRAGMA busy_timeout=5000"))
        Base.metadata.create_all(self.engine)
        self._ensure_cache_entry_columns()
        self._ensure_whitelist_entry_columns()
        self._ensure_prefetch_job_columns()
        self._ensure_task_entry_columns()

    def _ensure_cache_entry_columns(self) -> None:
        columns = {
            "title": "TEXT",
            "source_link": "TEXT",
            "poster": "TEXT",
            "category": "VARCHAR(64)",
            "priority": "INTEGER DEFAULT 100",
            "max_attempts": "INTEGER DEFAULT 3",
            "trigger": "VARCHAR(32)",
            "content_type": "VARCHAR(32)",
            "content_id": "TEXT",
            "available_at": "FLOAT",
            "claimed_at": "FLOAT",
            "claimed_by": "VARCHAR(128)",
            "processing_expires_at": "FLOAT",
        }
        with self.engine.begin() as connection:
            existing = {
                row[1]
                for row in connection.execute(text("PRAGMA table_info(cache_entries)"))
            }
            for column_name, column_sql in columns.items():
                if column_name in existing:
                    continue
                connection.execute(text(f"ALTER TABLE cache_entries ADD COLUMN {column_name} {column_sql}"))

    def _ensure_whitelist_entry_columns(self) -> None:
        columns = {
            "media_title": "VARCHAR(255)",
        }
        with self.engine.begin() as connection:
            existing = {
                row[1]
                for row in connection.execute(text("PRAGMA table_info(whitelist_entries)"))
            }
            for column_name, column_sql in columns.items():
                if column_name in existing:
                    continue
                connection.execute(text(f"ALTER TABLE whitelist_entries ADD COLUMN {column_name} {column_sql}"))

    def _ensure_prefetch_job_columns(self) -> None:
        columns = {
            "claimed_by": "VARCHAR(128)",
            "claimed_at": "FLOAT",
            "processing_expires_at": "FLOAT",
            "attempt": "INTEGER DEFAULT 0",
            "max_attempts": "INTEGER DEFAULT 3",
            "last_error": "TEXT",
        }
        with self.engine.begin() as connection:
            tables = {
                row[0]
                for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            }
            if "prefetch_jobs" not in tables:
                return
            existing = {
                row[1]
                for row in connection.execute(text("PRAGMA table_info(prefetch_jobs)"))
            }
            for column_name, column_sql in columns.items():
                if column_name in existing:
                    continue
                connection.execute(text(f"ALTER TABLE prefetch_jobs ADD COLUMN {column_name} {column_sql}"))

    def _ensure_task_entry_columns(self) -> None:
        columns = {
            "claimed_by": "VARCHAR(128)",
            "claimed_at": "FLOAT",
            "processing_expires_at": "FLOAT",
            "attempt": "INTEGER DEFAULT 0",
            "max_attempts": "INTEGER DEFAULT 3",
            "last_error": "TEXT",
        }
        with self.engine.begin() as connection:
            tables = {
                row[0]
                for row in connection.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
            }
            if "task_entry" not in tables:
                return
            existing = {
                row[1]
                for row in connection.execute(text("PRAGMA table_info(task_entry)"))
            }
            for column_name, column_sql in columns.items():
                if column_name in existing:
                    continue
                connection.execute(text(f"ALTER TABLE task_entry ADD COLUMN {column_name} {column_sql}"))


