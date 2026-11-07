"""SQLite connections whose context manager also guarantees closure.

The stdlib sqlite3 connection context manager commits or rolls back, but it
intentionally does not close the connection. Shoir-IE uses context-manager
blocks as scoped database operations throughout its local persistence layer.
This subclass preserves transaction semantics and closes the connection at
block exit so file handles are released deterministically.
"""
from __future__ import annotations

import sqlite3
from typing import Any


class ClosingSQLiteConnection(sqlite3.Connection):
    """Connection that closes after its normal commit/rollback context exit."""

    def __del__(self) -> None:
        """Close an abandoned connection before sqlite3 emits an unclosed-handle warning."""
        try:
            self.close()
        except Exception:
            # Finalizers must not leak errors during interpreter shutdown.
            pass

    def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> Any:
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            try:
                self.close()
            except sqlite3.Error:
                # Preserve the original transaction exception if close itself
                # reports that the connection was already closed.
                pass


def sqlite_connect(database: Any, *args: Any, **kwargs: Any) -> ClosingSQLiteConnection:
    """Open an sqlite3 connection with deterministic close-on-context-exit.

    Callers that need a long-lived connection can still manage its lifetime
    explicitly with try/finally and close().
    """
    kwargs.setdefault("factory", ClosingSQLiteConnection)
    return sqlite3.connect(database, *args, **kwargs)
