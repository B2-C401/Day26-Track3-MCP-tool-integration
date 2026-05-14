import os
import pytest

import psycopg

from implementation.db.postgres_adapter import PostgresAdapter
from ._adapter_contract import AdapterContract

PG_DSN = os.getenv("PG_DSN")

pytestmark = pytest.mark.skipif(
    PG_DSN is None,
    reason="Set PG_DSN to run Postgres adapter tests (e.g., docker compose up)",
)


@pytest.fixture
def adapter():
    """
    Yield a PostgresAdapter that rolls back any inserts after each test.

    The adapter's insert() method calls conn.commit() to persist data. We
    monkeypatch commit() to be a no-op for the duration of the test so that
    all writes stay in the open transaction. After the test we roll back the
    whole transaction so the seeded rows remain intact for subsequent tests.
    """
    a = PostgresAdapter(PG_DSN)
    # Suppress commits so inserts stay in the open transaction.
    a._conn.commit = lambda: None  # type: ignore[method-assign]
    yield a
    # Roll back the unsuppressed transaction, discarding all test inserts.
    a._conn.commit = psycopg.Connection.commit.__get__(a._conn)  # restore
    a._conn.rollback()
    a.close()


class TestPostgresContract(AdapterContract):
    pass
