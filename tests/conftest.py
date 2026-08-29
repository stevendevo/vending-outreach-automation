import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from vending_outreach.store import Store  # noqa: E402

# Set TEST_DATABASE_URL to run the whole suite against a real Postgres, which
# is what Replit deployments use. Unset, everything runs on SQLite.
TEST_DSN = os.getenv("TEST_DATABASE_URL", "")


@pytest.fixture
def store(tmp_path):
    """A clean Store on whichever backend is being exercised."""
    if TEST_DSN:
        s = Store(dsn=TEST_DSN)
        # Deployments reuse one database, so isolate tests by emptying it.
        for table in ("sends", "outreach", "contacts", "properties"):
            s.conn.execute(f"DELETE FROM {table}")
        s.conn.commit()
    else:
        s = Store(tmp_path / "t.sqlite3")
    yield s
    s.close()


@pytest.fixture
def backend(store):
    return store.backend
