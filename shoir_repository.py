"""Shoir-IE repository adapter.

All legacy local SQLite access goes through this module. New platform records use
the platform core's remote-first repository when DATABASE_URL is configured.
This separation keeps offline compatibility while eliminating scattered SQLite
configuration and connection behavior.
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from typing import Iterator

DEFAULT_DB_PATH = os.getenv("SHOIR_SQLITE_PATH", "enterprise_full_workspace.db")


def sqlite_connect(path: str | None = None, timeout: int = 30) -> sqlite3.Connection:
    conn = sqlite3.connect(
        path or DEFAULT_DB_PATH,
        timeout=max(1, int(timeout)),
        check_same_thread=False,
    )
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


@contextmanager
def local_transaction(path: str | None = None, timeout: int = 30) -> Iterator[sqlite3.Connection]:
    conn = sqlite_connect(path, timeout)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def local_db_path() -> str:
    return DEFAULT_DB_PATH


__all__ = ["sqlite_connect", "local_transaction", "local_db_path", "DEFAULT_DB_PATH"]
