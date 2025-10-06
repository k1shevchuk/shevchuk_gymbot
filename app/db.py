from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    """Declarative base for ORM models."""


_settings = get_settings()
engine = create_engine(_settings.database_url, future=True, echo=False)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


class Database:
    """Helper wrapper to run blocking ORM calls in a thread pool."""

    def __init__(self, session_factory: Callable[[], Session]):
        self._session_factory = session_factory

    def _run_sync(self, func: Callable[[Session], Any]) -> Any:
        with self._session_factory() as session:
            try:
                result = func(session)
                session.commit()
                return result
            except Exception:
                session.rollback()
                raise

    async def run(self, func: Callable[[Session], Any]) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._run_sync, func)

    def _execute_no_commit(self, func: Callable[[Session], Any]) -> Any:
        with self._session_factory() as session:
            return func(session)

    async def run_without_commit(self, func: Callable[[Session], Any]) -> Any:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._execute_no_commit, func)


_db_instance: Optional[Database] = None


def get_db() -> Database:
    global _db_instance
    if _db_instance is None:
        _db_instance = Database(SessionLocal)
    return _db_instance
