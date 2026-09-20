import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from stremio_http_proxy.entity.base import Base
# Import all entities to register them with Base.metadata
from stremio_http_proxy.entity.cache_entry import CacheEntry  # noqa: F401
from stremio_http_proxy.entity.media import Media  # noqa: F401
from stremio_http_proxy.entity.media_item import MediaItem  # noqa: F401
from stremio_http_proxy.entity.playback_history import PlaybackHistory  # noqa: F401
from stremio_http_proxy.entity.task_entry import TaskEntry  # noqa: F401


class DbManager:
    def __init__(self, sqlite_path: str | None = None, db_url: str | None = None, auto_migrate: bool = True):
        env_db_url = os.environ.get("DATABASE_URL")
        self.db_url = db_url or env_db_url

        if not self.db_url:
            path = sqlite_path or "var/db/stremio_http_proxy.db"
            p = Path(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            self.db_url = f"sqlite:///{p.resolve()}"

        if self.db_url.startswith("sqlite"):
            self.engine = create_engine(
                self.db_url,
                connect_args={"check_same_thread": False},
            )
        else:
            self.engine = create_engine(
                self.db_url,
                pool_pre_ping=True,
                pool_recycle=3600,
                pool_size=10,
                max_overflow=20,
            )

        self.session_factory = sessionmaker(bind=self.engine, expire_on_commit=False)
        self._initialize(auto_migrate=auto_migrate)

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

    def _initialize(self, auto_migrate: bool = True) -> None:
        if self.db_url.startswith("sqlite") and ":memory:" not in self.db_url:
            with self.engine.begin() as connection:
                connection.execute(text("PRAGMA journal_mode=WAL"))
                connection.execute(text("PRAGMA synchronous=NORMAL"))
                connection.execute(text("PRAGMA busy_timeout=5000"))

        if auto_migrate:
            try:
                self.run_migrations()
            except Exception:
                # Fallback to create_all for in-memory / non-alembic test setups
                Base.metadata.create_all(self.engine)
        else:
            Base.metadata.create_all(self.engine)

    def run_migrations(self) -> None:
        alembic_ini_path = Path("alembic.ini")
        if not alembic_ini_path.exists():
            # Check parent directory or project root
            for parent in Path(__file__).resolve().parents:
                candidate = parent / "alembic.ini"
                if candidate.exists():
                    alembic_ini_path = candidate
                    break

        if not alembic_ini_path.exists():
            Base.metadata.create_all(self.engine)
            return

        alembic_cfg = Config(str(alembic_ini_path))
        alembic_cfg.set_main_option("sqlalchemy.url", self.db_url)
        command.upgrade(alembic_cfg, "head")
