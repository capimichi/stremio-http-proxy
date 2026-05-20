from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from stremio_http_proxy.entity.cache_entry import Base


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
