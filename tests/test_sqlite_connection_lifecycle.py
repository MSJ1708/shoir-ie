"""Regression tests for deterministic SQLite connection lifecycle."""
from __future__ import annotations

import sqlite3

import pytest

from shoir_sqlite import connect


def test_context_manager_commits_and_closes_connection(tmp_path):
    path = tmp_path / "committed.db"
    with connect(path, timeout=5) as conn:
        conn.execute("CREATE TABLE sample (value INTEGER NOT NULL)")
        conn.execute("INSERT INTO sample(value) VALUES (7)")

    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        conn.execute("SELECT value FROM sample")

    with connect(path, timeout=5) as check:
        assert check.execute("SELECT value FROM sample").fetchone() == (7,)


def test_context_manager_rolls_back_and_closes_after_exception(tmp_path):
    path = tmp_path / "rolled-back.db"
    conn = None
    with pytest.raises(RuntimeError, match="force rollback"):
        with connect(path, timeout=5) as active:
            conn = active
            active.execute("CREATE TABLE sample (value INTEGER NOT NULL)")
            active.execute("INSERT INTO sample(value) VALUES (11)")
            raise RuntimeError("force rollback")

    assert conn is not None
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        conn.execute("SELECT value FROM sample")

    with connect(path, timeout=5) as check:
        table = check.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sample'"
        ).fetchone()
        assert table is None


def test_abandoned_connection_is_closed_by_finalizer_without_resource_warning(tmp_path):
    import gc
    import warnings

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", ResourceWarning)
        connection = connect(tmp_path / "finalized.db", timeout=5)
        connection.execute("CREATE TABLE sample (value INTEGER)")
        del connection
        gc.collect()

    assert not [warning for warning in captured if issubclass(warning.category, ResourceWarning)]
