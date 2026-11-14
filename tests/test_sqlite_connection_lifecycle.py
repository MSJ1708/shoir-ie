"""Regression tests for deterministic SQLite connection lifecycle.

The application intentionally treats a with block as a scoped database
operation. The wrapper must preserve sqlite3 commit/rollback behaviour and
close the underlying handle even though sqlite3.Connection.__exit__ does not.
"""
from __future__ import annotations

import gc
import sqlite3
import warnings

import pytest

from shoir_sqlite import sqlite_connect


def test_context_manager_commits_and_closes_connection(tmp_path):
    database = tmp_path / "committed.sqlite"
    with sqlite_connect(database, timeout=5) as conn:
        conn.execute("CREATE TABLE sample(value INTEGER NOT NULL)")
        conn.execute("INSERT INTO sample(value) VALUES (7)")

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        conn.execute("SELECT value FROM sample")

    with sqlite_connect(database, timeout=5) as check:
        assert check.execute("SELECT value FROM sample").fetchone() == (7,)


def test_context_manager_rolls_back_and_closes_after_exception(tmp_path):
    database = tmp_path / "rolled-back.sqlite"
    connection = None

    with pytest.raises(RuntimeError, match="force rollback"):
        with sqlite_connect(database, timeout=5) as active:
            connection = active
            # sqlite3's legacy transaction mode does not necessarily begin a
            # transaction for DDL alone. Start one explicitly so this test
            # verifies transactional DDL rollback rather than SQLite's
            # implicit-transaction rules.
            active.execute("BEGIN")
            active.execute("CREATE TABLE sample(value INTEGER NOT NULL)")
            active.execute("INSERT INTO sample(value) VALUES (11)")
            raise RuntimeError("force rollback")

    assert connection is not None
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connection.execute("SELECT value FROM sample")

    with sqlite_connect(database, timeout=5) as check:
        table = check.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sample'"
        ).fetchone()
        assert table is None


def test_explicit_close_is_idempotent(tmp_path):
    connection = sqlite_connect(tmp_path / "explicit-close.sqlite", timeout=5)
    connection.execute("CREATE TABLE sample(value INTEGER)")
    connection.close()
    connection.close()
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        connection.execute("SELECT value FROM sample")


def test_abandoned_connection_finalizer_closes_without_resource_warning(tmp_path):
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", ResourceWarning)
        connection = sqlite_connect(tmp_path / "finalized.sqlite", timeout=5)
        connection.execute("CREATE TABLE sample(value INTEGER)")
        del connection
        gc.collect()

    leaked = [
        warning for warning in captured
        if issubclass(warning.category, ResourceWarning)
    ]
    assert not leaked
