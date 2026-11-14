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

def test_nested_savepoint_rollback_preserves_outer_transaction(tmp_path):
    database = tmp_path / "savepoint.sqlite"
    with sqlite_connect(database, timeout=5) as conn:
        conn.execute("CREATE TABLE sample(value INTEGER NOT NULL)")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT INTO sample(value) VALUES (1)")
        conn.execute("SAVEPOINT nested_change")
        conn.execute("INSERT INTO sample(value) VALUES (2)")
        conn.execute("ROLLBACK TO SAVEPOINT nested_change")
        conn.execute("RELEASE SAVEPOINT nested_change")
        conn.execute("INSERT INTO sample(value) VALUES (3)")

    with sqlite_connect(database, timeout=5) as check:
        values = [row[0] for row in check.execute("SELECT value FROM sample ORDER BY value")]
    assert values == [1, 3]


def test_busy_timeout_releases_writer_lock_and_allows_retry(tmp_path):
    database = tmp_path / "busy-timeout.sqlite"
    with sqlite_connect(database, timeout=0.05) as setup:
        setup.execute("CREATE TABLE sample(value INTEGER NOT NULL)")

    with sqlite_connect(database, timeout=0.05) as writer, sqlite_connect(database, timeout=0.05) as contender:
        writer.execute("BEGIN IMMEDIATE")
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            contender.execute("BEGIN IMMEDIATE")

        writer.rollback()
        contender.execute("BEGIN IMMEDIATE")
        contender.execute("INSERT INTO sample(value) VALUES (7)")
        contender.commit()

    with sqlite_connect(database, timeout=5) as check:
        assert check.execute("SELECT value FROM sample").fetchone() == (7,)


def test_wal_checkpoint_and_reopen_preserve_committed_rows(tmp_path):
    database = tmp_path / "wal-checkpoint.sqlite"
    with sqlite_connect(database, timeout=5) as conn:
        mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
        assert str(mode).casefold() == "wal"
        conn.execute("CREATE TABLE sample(value INTEGER NOT NULL)")
        conn.executemany("INSERT INTO sample(value) VALUES (?)", [(1,), (2,), (3,)])
        conn.commit()
        busy, log_frames, checkpointed_frames = conn.execute(
            "PRAGMA wal_checkpoint(TRUNCATE)"
        ).fetchone()
        assert busy == 0
        assert checkpointed_frames <= log_frames

    with sqlite_connect(database, timeout=5) as reopened:
        assert [row[0] for row in reopened.execute("SELECT value FROM sample ORDER BY value")] == [1, 2, 3]
        assert reopened.execute("PRAGMA quick_check").fetchone()[0] == "ok"


def test_platform_schema_initialization_is_repeatable_on_a_fresh_database(tmp_path):
    from industrial_platform import init_platform_db

    database = str(tmp_path / "fresh-platform.sqlite")
    assert init_platform_db(database) is True
    assert init_platform_db(database) is True

    with sqlite_connect(database, timeout=5) as conn:
        model_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(platform_models)")
        }
        assert {"dataset_id", "run_id", "solver_version", "result_hash"}.issubset(model_columns)
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"

