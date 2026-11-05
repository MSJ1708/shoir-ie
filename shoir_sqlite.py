"""SQLite connection factory that preserves transaction semantics and closes on context exit.

The standard sqlite3 connection context manager commits or rolls back but does not
close the connection. This subclass makes the common `with connect(...)` pattern
release file descriptors deterministically while retaining sqlite3.Connection
compatibility for callers that use execute(), cursor(), or explicit close().
"""
from __future__ import annotations

import sqlite3
from typing import Any


class ClosingSQLiteConnection(sqlite3.Connection):
    """A SQLite connection that always closes after its context manager exits."""

    def __del__(self) -> None:
        """Close a forgotten connection before sqlite3's unclosed-handle warning."""
        try:
            self.close()
        except Exception:
            # Finalizers must not leak errors during interpreter shutdown.
            pass

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> bool | None:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect(*args: Any, **kwargs: Any) -> sqlite3.Connection:
    """Create a normal SQLite connection with deterministic context cleanup."""
    kwargs.setdefault("factory", ClosingSQLiteConnection)
    return sqlite3.connect(*args, **kwargs)
