"""Single local repository gateway for Shoir-IE.

The platform layer imports this module instead of opening SQLite connections
directly.  PostgreSQL remains the authoritative backend when configured by the
platform core; this gateway owns only the compatibility/offline SQLite path.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Union


PathLike = Union[str, Path]


def sqlite_connect(path: PathLike = "enterprise_full_workspace.db", timeout: int = 30) -> sqlite3.Connection:
    """Open a consistently configured SQLite connection.

    This is intentionally small: schema ownership stays with the service that
    owns each table, while connection policy is centralized here.
    """
    db_path = Path(path).expanduser()
    if db_path.parent and str(db_path.parent) not in ("", "."):
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=max(1, int(timeout)), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn
