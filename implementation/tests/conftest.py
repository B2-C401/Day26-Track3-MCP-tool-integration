import pytest
from pathlib import Path

from implementation import init_db
from implementation.db.sqlite_adapter import SQLiteAdapter


@pytest.fixture
def seeded_sqlite_path(tmp_path: Path) -> Path:
    db = tmp_path / "lab.db"
    init_db.create_schema(db)
    init_db.seed(db)
    return db


@pytest.fixture
def sqlite_adapter(seeded_sqlite_path):
    adapter = SQLiteAdapter(str(seeded_sqlite_path))
    yield adapter
    adapter.close()
