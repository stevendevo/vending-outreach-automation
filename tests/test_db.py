"""The SQL in store.py is written once and must run on both backends.
These pin the three things that actually differ."""
import pytest

from vending_outreach.db import DB, POSTGRES, SQLITE, detect_backend


def test_detects_postgres_from_a_replit_style_url():
    assert detect_backend("postgresql://user:pw@host/db") == POSTGRES
    assert detect_backend("postgres://user:pw@host/db") == POSTGRES


def test_falls_back_to_sqlite_without_a_database_url():
    assert detect_backend("") == SQLITE


@pytest.fixture
def pg(tmp_path):
    """A DB object forced into Postgres dialect without connecting."""
    db = DB.__new__(DB)
    db.backend = POSTGRES
    return db


def test_placeholders_are_rewritten_for_postgres(pg):
    assert pg.translate("SELECT * FROM t WHERE a = ? AND b = ?") == \
        "SELECT * FROM t WHERE a = %s AND b = %s"


def test_question_marks_inside_string_literals_are_left_alone(pg):
    """Our templates and subjects contain '?' -- rewriting one inside a quoted
    literal would corrupt the query."""
    sql = "SELECT * FROM t WHERE subject = 'food truck night?' AND a = ?"
    out = pg.translate(sql)
    assert "'food truck night?'" in out
    assert out.endswith("a = %s")


def test_two_arg_max_becomes_greatest(pg):
    out = pg.translate("SET rating_count = MAX(excluded.rating_count, properties.rating_count)")
    assert "GREATEST(excluded.rating_count, properties.rating_count)" in out
    assert "MAX(" not in out


def test_autoincrement_becomes_bigserial(pg):
    assert "BIGSERIAL PRIMARY KEY" in pg.translate("id INTEGER PRIMARY KEY AUTOINCREMENT")


def test_sqlite_dialect_is_passed_through_untouched():
    db = DB.__new__(DB)
    db.backend = SQLITE
    sql = "SELECT ? , MAX(a,b) FROM t"
    assert db.translate(sql) == sql
