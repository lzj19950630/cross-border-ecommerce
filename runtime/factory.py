"""存储/服务工厂：CLI 与 FastAPI 共用。"""
from __future__ import annotations

import os

from .storage import SQLiteStore, TaskStore

DEFAULT_DB = ".runtime/runtime.db"


def make_store(db: str | None = None, db_url: str | None = None) -> TaskStore:
    """优先级：显式 db 路径 > RUNTIME_DB_URL / db_url > 默认 SQLite。"""
    if db:
        return SQLiteStore(db)
    url = db_url or os.environ.get("RUNTIME_DB_URL")
    if url:
        from .integrations.sqlalchemy_store import SQLAlchemyStore
        return SQLAlchemyStore(url)
    return SQLiteStore(os.environ.get("RUNTIME_DB") or DEFAULT_DB)
