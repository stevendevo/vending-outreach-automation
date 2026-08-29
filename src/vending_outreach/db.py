"""Database abstraction over SQLite and PostgreSQL.

Replit Scheduled Deployments run on an ephemeral filesystem: anything written
to disk is gone by the next run. That is fatal for this pipeline, whose whole
no-double-send guarantee rests on remembering what it already sent. So when
DATABASE_URL is present (Replit's managed Postgres) we use it, and fall back to
a local SQLite file for development and workspace runs.

The SQL in store.py is written once and runs on both. Only three things differ,
and they are handled here: parameter style, autoincrement, and two-argument MAX.
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Optional

SQLITE = "sqlite"
POSTGRES = "postgres"


def detect_backend(db_url: Optional[str] = None) -> str:
    url = db_url if db_url is not None else os.getenv("DATABASE_URL", "")
    return POSTGRES if url.startswith(("postgres://", "postgresql://")) else SQLITE


class Cursor:
    """Wraps a driver cursor so rows are always mapping-like."""

    def __init__(self, cur, backend: str):
        self._cur = cur
        self._backend = backend

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    def __iter__(self):
        return iter(self._cur)

    @property
    def rowcount(self) -> int:
        return self._cur.rowcount


class DB:
    """Minimal connection wrapper. Exposes execute/commit/rollback/close."""

    def __init__(self, dsn: str = "", sqlite_path: str | Path = ""):
        self.backend = detect_backend(dsn or None)
        if self.backend == POSTGRES:
            try:
                import psycopg
                from psycopg.rows import dict_row
            except ImportError as exc:  # pragma: no cover - env-dependent
                raise SystemExit(
                    "DATABASE_URL is set but psycopg is not installed.\n"
                    "Add `psycopg[binary]` to requirements.txt."
                ) from exc
            self._conn = psycopg.connect(dsn or os.environ["DATABASE_URL"],
                                         row_factory=dict_row, autocommit=False)
        else:
            path = Path(sqlite_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(path)
            self._conn.row_factory = sqlite3.Row

    # ------------------------------------------------------------- dialect
    def translate(self, sql: str) -> str:
        """Rewrite portable SQL into the active dialect."""
        if self.backend == SQLITE:
            return sql
        # Postgres uses %s placeholders. Only rewrite ? that are real
        # placeholders, never one inside a quoted string literal.
        out, in_str = [], False
        for ch in sql:
            if ch == "'":
                in_str = not in_str
            if ch == "?" and not in_str:
                out.append("%s")
            else:
                out.append(ch)
        sql = "".join(out)
        # SQLite's two-argument MAX is GREATEST in Postgres.
        sql = re.sub(r"\bMAX\(([^()]+),([^()]+)\)", r"GREATEST(\1,\2)", sql)
        sql = sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT",
                          "BIGSERIAL PRIMARY KEY")
        return sql

    # ------------------------------------------------------------- execute
    def execute(self, sql: str, params: Iterable[Any] = ()) -> Cursor:
        cur = self._conn.cursor()
        cur.execute(self.translate(sql), tuple(params))
        return Cursor(cur, self.backend)

    def executescript(self, script: str) -> None:
        if self.backend == SQLITE:
            self._conn.executescript(script)
            return
        cur = self._conn.cursor()
        for statement in [s.strip() for s in script.split(";") if s.strip()]:
            cur.execute(self.translate(statement))

    def commit(self) -> None:
        self._conn.commit()

    def rollback(self) -> None:
        self._conn.rollback()

    def close(self) -> None:
        self._conn.close()

    @property
    def describe(self) -> str:
        if self.backend == POSTGRES:
            return "PostgreSQL (persistent)"
        return "SQLite (local file)"
