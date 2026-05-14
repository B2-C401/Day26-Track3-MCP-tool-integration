# MCP SQLite Lab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FastMCP SQLite lab end-to-end (100 base + 10 bonus): `search` / `insert` / `aggregate` tools, `schema://` resources, Bearer-auth HTTP transport, swappable SQLite/Postgres adapters, pytest suite, and `verify_server.py` smoke test.

**Architecture:** Three layers — `mcp_server.py` (FastMCP decorators only), `db/` package (`DatabaseAdapter` ABC + SQLite/Postgres implementations + shared `validators.py`), and an `auth.py` Bearer middleware activated only on HTTP transport. Identifiers are validated against the live schema before any SQL is built; values always go through driver placeholders.

**Tech Stack:** Python 3.11+, `uv` package manager, `fastmcp`, `psycopg[binary]` (Postgres bonus), `pytest`, SQLite stdlib, Docker Compose (Postgres bonus, isolated under project name `mcp-sqlite-lab`).

**Spec reference:** `docs/superpowers/specs/2026-05-14-mcp-sqlite-lab-design.md`

**Commit policy:** Per user preference, no intermediate commits during this work. The final task creates one consolidated commit at the end with no Co-Authored-By trailer.

---

## File Structure

| Path | Responsibility |
|---|---|
| `pyproject.toml` | uv-managed deps + scripts |
| `implementation/__init__.py` | Package marker |
| `implementation/db/__init__.py` | Re-export `DatabaseAdapter`, `SQLiteAdapter`, `PostgresAdapter`, error classes |
| `implementation/db/errors.py` | `ValidationError`, `AdapterError` |
| `implementation/db/validators.py` | Identifier / operator / metric whitelists, schema-aware checks |
| `implementation/db/base.py` | `DatabaseAdapter` ABC |
| `implementation/db/sqlite_adapter.py` | `SQLiteAdapter` impl |
| `implementation/db/postgres_adapter.py` | `PostgresAdapter` impl |
| `implementation/init_db.py` | Create + seed SQLite DB |
| `implementation/auth.py` | `BearerAuthMiddleware` for HTTP transport |
| `implementation/mcp_server.py` | FastMCP entrypoint, tools, resources, CLI |
| `implementation/verify_server.py` | E2E smoke test, PASS/FAIL output |
| `implementation/tests/conftest.py` | pytest fixtures (in-memory SQLite, MCP test client) |
| `implementation/tests/test_validators.py` | Unit tests for validators |
| `implementation/tests/test_sqlite_adapter.py` | Integration tests, in-memory SQLite |
| `implementation/tests/_adapter_contract.py` | Shared test base class run against both adapters |
| `implementation/tests/test_postgres_adapter.py` | Postgres adapter via `PG_DSN`, skipped otherwise |
| `implementation/tests/test_tools.py` | In-process FastMCP client tests |
| `implementation/tests/test_resources.py` | Resource list + read tests |
| `implementation/tests/test_auth.py` | HTTP auth tests |
| `docker/docker-compose.yml` | Isolated Postgres service |
| `docker/init.sql` | Schema + seed parity with SQLite |
| `scripts/teardown.sh` | `docker compose down -v --remove-orphans` |
| `scripts/run-inspector.sh` | npx inspector with absolute paths |
| `.mcp.json` | Claude Code sample config |
| `README.md` | Rewritten with setup, demo, teardown |

---

## Task 1: Project Scaffold and Dependencies

**Files:**
- Create: `pyproject.toml`
- Create: `implementation/__init__.py`
- Create: `implementation/tests/__init__.py`
- Create: `implementation/db/__init__.py`

- [ ] **Step 1: Verify `uv` is available**

Run: `uv --version`
Expected: prints a version like `uv 0.5.x`. If missing, install with `curl -LsSf https://astral.sh/uv/install.sh | sh` and re-open shell.

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "mcp-sqlite-lab"
version = "0.1.0"
description = "Day 26 Track 3 — FastMCP server backed by SQLite"
requires-python = ">=3.11"
dependencies = [
    "fastmcp>=2.0",
]

[project.optional-dependencies]
postgres = ["psycopg[binary]>=3.2"]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "httpx>=0.27",  # for test_auth.py HTTP requests
]

[tool.pytest.ini_options]
testpaths = ["implementation/tests"]
asyncio_mode = "auto"

[tool.uv]
package = false  # source-layout, no install needed
```

- [ ] **Step 3: Create empty package markers**

`implementation/__init__.py`:
```python
```

`implementation/tests/__init__.py`:
```python
```

`implementation/db/__init__.py`:
```python
"""Database adapter layer. SQL stays here; MCP stays out."""
```

- [ ] **Step 4: Install dependencies**

Run: `uv sync --extra dev --extra postgres`
Expected: creates `.venv/`, installs fastmcp, psycopg, pytest, httpx.

- [ ] **Step 5: Smoke check Python imports**

Run: `uv run python -c "import fastmcp, psycopg, pytest, httpx; print('ok')"`
Expected: `ok`

---

## Task 2: Error Types

**Files:**
- Create: `implementation/db/errors.py`
- Create: `implementation/tests/test_validators.py` (start)

- [ ] **Step 1: Write `db/errors.py`**

```python
"""Database layer exceptions, decoupled from FastMCP."""


class DBError(Exception):
    """Base for adapter-related failures."""


class ValidationError(DBError):
    """Raised when user input cannot be safely turned into SQL."""


class AdapterError(DBError):
    """Raised when the underlying database driver fails."""
```

- [ ] **Step 2: Smoke import**

Run: `uv run python -c "from implementation.db.errors import ValidationError, AdapterError; print('ok')"`
Expected: `ok`

---

## Task 3: Validators (TDD)

**Files:**
- Create: `implementation/db/validators.py`
- Modify: `implementation/tests/test_validators.py`

- [ ] **Step 1: Write failing tests for `validate_identifier`**

`implementation/tests/test_validators.py`:
```python
import pytest
from implementation.db.errors import ValidationError
from implementation.db.validators import (
    validate_identifier,
    validate_metric,
    ALLOWED_OPERATORS,
    ALLOWED_METRICS,
)


class TestValidateIdentifier:
    @pytest.mark.parametrize("name", ["users", "_x", "col1", "Students", "table_2"])
    def test_accepts_valid_identifier(self, name):
        assert validate_identifier(name) == name

    @pytest.mark.parametrize("bad", [
        "",
        "1foo",
        "foo bar",
        "foo;bar",
        "foo'",
        'foo"',
        "foo-bar",
        "foo;DROP TABLE users",
        "--",
        "OR 1=1",
    ])
    def test_rejects_invalid_identifier(self, bad):
        with pytest.raises(ValidationError):
            validate_identifier(bad)


class TestValidateMetric:
    @pytest.mark.parametrize("m", ["count", "avg", "sum", "min", "max"])
    def test_accepts_lowercase_metric(self, m):
        assert validate_metric(m) == m

    @pytest.mark.parametrize("m", ["COUNT", "Avg", "median", "", "select"])
    def test_rejects_unknown_metric(self, m):
        with pytest.raises(ValidationError):
            validate_metric(m)


def test_operator_whitelist_is_immutable_set():
    assert isinstance(ALLOWED_OPERATORS, frozenset)
    assert "=" in ALLOWED_OPERATORS
    assert "OR" not in ALLOWED_OPERATORS


def test_metric_whitelist_is_immutable_set():
    assert isinstance(ALLOWED_METRICS, frozenset)
    assert ALLOWED_METRICS == frozenset({"count", "avg", "sum", "min", "max"})
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `uv run pytest implementation/tests/test_validators.py -v`
Expected: ImportError / module not found for `validators`.

- [ ] **Step 3: Implement `validators.py` (level 1: pure functions)**

```python
"""Validation helpers. Identifier checks here are syntactic + whitelist;
schema-aware checks (validate_table, validate_columns, validate_filters,
validate_insert_values) live below and need an adapter."""

import re
from typing import Any, Iterable

from .errors import ValidationError

ALLOWED_OPERATORS: frozenset[str] = frozenset({"=", "!=", "<", "<=", ">", ">=", "LIKE", "IN"})
ALLOWED_METRICS: frozenset[str] = frozenset({"count", "avg", "sum", "min", "max"})

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def validate_identifier(name: str) -> str:
    if not isinstance(name, str) or not _IDENTIFIER_RE.match(name):
        raise ValidationError(f"invalid identifier: {name!r}")
    return name


def validate_metric(metric: str) -> str:
    if not isinstance(metric, str) or metric not in ALLOWED_METRICS:
        raise ValidationError(
            f"unsupported metric: {metric!r}; allowed: {sorted(ALLOWED_METRICS)}"
        )
    return metric
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `uv run pytest implementation/tests/test_validators.py -v`
Expected: all tests PASS (15+ items).

- [ ] **Step 5: Add schema-aware validator tests**

Append to `implementation/tests/test_validators.py`:

```python
class FakeAdapter:
    """Minimal stand-in for an adapter — only the methods validators call."""
    def __init__(self, schema):
        self._schema = schema  # {table: [col, ...]}

    def list_tables(self):
        return list(self._schema)

    def get_table_schema(self, table):
        return [{"name": c} for c in self._schema[table]]


@pytest.fixture
def adapter():
    return FakeAdapter({
        "students": ["id", "name", "cohort", "score"],
        "courses": ["id", "title", "credits"],
    })


class TestValidateTable:
    def test_accepts_known_table(self, adapter):
        from implementation.db.validators import validate_table
        assert validate_table(adapter, "students") == "students"

    def test_rejects_unknown_table(self, adapter):
        from implementation.db.validators import validate_table
        with pytest.raises(ValidationError):
            validate_table(adapter, "ghosts")

    def test_rejects_syntactically_bad_table(self, adapter):
        from implementation.db.validators import validate_table
        with pytest.raises(ValidationError):
            validate_table(adapter, "students;")


class TestValidateColumns:
    def test_accepts_known_columns(self, adapter):
        from implementation.db.validators import validate_columns
        assert validate_columns(adapter, "students", ["id", "name"]) == ["id", "name"]

    def test_rejects_unknown_column(self, adapter):
        from implementation.db.validators import validate_columns
        with pytest.raises(ValidationError):
            validate_columns(adapter, "students", ["id", "ghost"])

    def test_empty_columns_means_all_columns(self, adapter):
        from implementation.db.validators import validate_columns
        assert validate_columns(adapter, "students", None) == ["id", "name", "cohort", "score"]


class TestValidateFilters:
    def test_accepts_valid_filter_list(self, adapter):
        from implementation.db.validators import validate_filters
        filters = [{"column": "cohort", "op": "=", "value": "A1"}]
        assert validate_filters(adapter, "students", filters) == filters

    def test_none_filters_returns_empty(self, adapter):
        from implementation.db.validators import validate_filters
        assert validate_filters(adapter, "students", None) == []

    def test_rejects_bad_operator(self, adapter):
        from implementation.db.validators import validate_filters
        with pytest.raises(ValidationError):
            validate_filters(adapter, "students", [{"column": "id", "op": "OR", "value": 1}])

    def test_rejects_unknown_column(self, adapter):
        from implementation.db.validators import validate_filters
        with pytest.raises(ValidationError):
            validate_filters(adapter, "students", [{"column": "ghost", "op": "=", "value": 1}])

    def test_requires_list_value_for_IN(self, adapter):
        from implementation.db.validators import validate_filters
        with pytest.raises(ValidationError):
            validate_filters(adapter, "students", [{"column": "id", "op": "IN", "value": 1}])


class TestValidateInsertValues:
    def test_accepts_known_columns(self, adapter):
        from implementation.db.validators import validate_insert_values
        vs = {"name": "Anh", "cohort": "A1"}
        assert validate_insert_values(adapter, "students", vs) == vs

    def test_rejects_empty(self, adapter):
        from implementation.db.validators import validate_insert_values
        with pytest.raises(ValidationError):
            validate_insert_values(adapter, "students", {})

    def test_rejects_unknown_column(self, adapter):
        from implementation.db.validators import validate_insert_values
        with pytest.raises(ValidationError):
            validate_insert_values(adapter, "students", {"ghost": 1})
```

- [ ] **Step 6: Run new tests, confirm failures**

Run: `uv run pytest implementation/tests/test_validators.py -v`
Expected: ImportError on new validator names.

- [ ] **Step 7: Extend `validators.py` with schema-aware validators**

Append to `implementation/db/validators.py`:

```python
def validate_table(adapter, table: str) -> str:
    validate_identifier(table)
    if table not in adapter.list_tables():
        raise ValidationError(f"unknown table: {table!r}")
    return table


def _columns_of(adapter, table: str) -> list[str]:
    return [c["name"] for c in adapter.get_table_schema(table)]


def validate_columns(adapter, table: str, columns: Iterable[str] | None) -> list[str]:
    known = _columns_of(adapter, table)
    if columns is None:
        return known
    cols = list(columns)
    if not cols:
        return known
    for c in cols:
        validate_identifier(c)
        if c not in known:
            raise ValidationError(f"unknown column on {table!r}: {c!r}")
    return cols


def validate_filters(adapter, table: str, filters: list[dict] | None) -> list[dict]:
    if filters is None:
        return []
    known = set(_columns_of(adapter, table))
    out: list[dict] = []
    for f in filters:
        if not isinstance(f, dict):
            raise ValidationError(f"filter must be an object, got {type(f).__name__}")
        col = f.get("column")
        op = f.get("op")
        if "value" not in f:
            raise ValidationError(f"filter missing 'value': {f!r}")
        value = f["value"]
        validate_identifier(col)
        if col not in known:
            raise ValidationError(f"unknown column on {table!r}: {col!r}")
        if op not in ALLOWED_OPERATORS:
            raise ValidationError(
                f"unsupported operator {op!r}; allowed: {sorted(ALLOWED_OPERATORS)}"
            )
        if op == "IN" and not isinstance(value, (list, tuple)):
            raise ValidationError("operator 'IN' requires a list value")
        out.append({"column": col, "op": op, "value": value})
    return out


def validate_insert_values(adapter, table: str, values: dict) -> dict:
    if not isinstance(values, dict) or not values:
        raise ValidationError("insert values must be a non-empty object")
    known = set(_columns_of(adapter, table))
    for k in values:
        validate_identifier(k)
        if k not in known:
            raise ValidationError(f"unknown column on {table!r}: {k!r}")
    return values
```

- [ ] **Step 8: Run tests, expect green**

Run: `uv run pytest implementation/tests/test_validators.py -v`
Expected: all tests PASS.

---

## Task 4: Database Adapter Interface

**Files:**
- Create: `implementation/db/base.py`
- Modify: `implementation/db/__init__.py`

- [ ] **Step 1: Write `db/base.py`**

```python
"""Abstract interface that SQLiteAdapter and PostgresAdapter both implement."""

from abc import ABC, abstractmethod
from typing import Any


class DatabaseAdapter(ABC):
    @abstractmethod
    def list_tables(self) -> list[str]: ...

    @abstractmethod
    def get_table_schema(self, table: str) -> list[dict[str, Any]]: ...

    @abstractmethod
    def get_full_schema(self) -> dict[str, list[dict[str, Any]]]: ...

    @abstractmethod
    def search(
        self,
        table: str,
        columns: list[str] | None = None,
        filters: list[dict] | None = None,
        order_by: str | None = None,
        descending: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> dict: ...

    @abstractmethod
    def insert(self, table: str, values: dict) -> dict: ...

    @abstractmethod
    def aggregate(
        self,
        table: str,
        metric: str,
        column: str | None = None,
        filters: list[dict] | None = None,
        group_by: str | None = None,
    ) -> dict: ...

    @abstractmethod
    def close(self) -> None: ...
```

- [ ] **Step 2: Update `db/__init__.py` to re-export**

```python
"""Database adapter layer. SQL stays here; MCP stays out."""

from .base import DatabaseAdapter
from .errors import AdapterError, DBError, ValidationError

__all__ = ["DatabaseAdapter", "DBError", "ValidationError", "AdapterError"]
```

- [ ] **Step 3: Smoke import**

Run: `uv run python -c "from implementation.db import DatabaseAdapter; print(DatabaseAdapter.__abstractmethods__)"`
Expected: prints a frozenset including `list_tables`, `search`, etc.

---

## Task 5: SQLite Adapter — list_tables & schema (TDD)

**Files:**
- Create: `implementation/init_db.py`
- Create: `implementation/db/sqlite_adapter.py`
- Create: `implementation/tests/conftest.py`
- Create: `implementation/tests/_adapter_contract.py`
- Create: `implementation/tests/test_sqlite_adapter.py`

- [ ] **Step 1: Write `init_db.py` (schema + seed)**

```python
"""Create and seed a SQLite database for the lab."""

from __future__ import annotations

import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS students (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name   TEXT    NOT NULL,
    cohort TEXT    NOT NULL,
    score  REAL    NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS courses (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    title   TEXT    NOT NULL,
    credits INTEGER NOT NULL DEFAULT 3
);

CREATE TABLE IF NOT EXISTS enrollments (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id INTEGER NOT NULL REFERENCES students(id),
    course_id  INTEGER NOT NULL REFERENCES courses(id),
    grade      REAL
);
"""

SEED_STUDENTS = [
    ("Anh",  "A1", 8.5),
    ("Binh", "A1", 7.0),
    ("Cuc",  "A1", 9.2),
    ("Dung", "A1", 6.5),
    ("Em",   "B2", 8.8),
    ("Phong","B2", 7.4),
    ("Giang","B2", 9.0),
    ("Hoa",  "B2", 5.5),
    ("Khanh","B2", 8.0),
    ("Linh", "B2", 6.8),
]
SEED_COURSES = [
    ("Algorithms",          4),
    ("Databases",           3),
    ("Operating Systems",   4),
    ("Distributed Systems", 3),
]
SEED_ENROLLMENTS = [
    (1, 1, 8.0), (1, 2, 9.0), (2, 1, 7.5), (3, 2, 9.5),
    (3, 3, 8.5), (4, 4, 6.0), (5, 1, 9.0), (5, 3, 8.0),
    (6, 2, 7.0), (7, 4, 9.5), (8, 1, 5.5), (8, 4, 6.0),
    (9, 2, 8.5), (10, 3, 7.0), (10, 4, 6.5),
]


def create_schema(db_path: str | Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()


def seed(db_path: str | Path) -> None:
    conn = sqlite3.connect(str(db_path))
    try:
        conn.executemany("INSERT INTO students(name, cohort, score) VALUES (?, ?, ?)", SEED_STUDENTS)
        conn.executemany("INSERT INTO courses(title, credits) VALUES (?, ?)", SEED_COURSES)
        conn.executemany(
            "INSERT INTO enrollments(student_id, course_id, grade) VALUES (?, ?, ?)",
            SEED_ENROLLMENTS,
        )
        conn.commit()
    finally:
        conn.close()


def main() -> None:
    db_path = Path("lab.db")
    if db_path.exists():
        db_path.unlink()
    create_schema(db_path)
    seed(db_path)
    print(f"Initialized {db_path.resolve()}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Write `tests/conftest.py`**

```python
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
```

- [ ] **Step 3: Write `tests/_adapter_contract.py` (shared test base)**

```python
"""Shared assertions for any DatabaseAdapter. Subclassed by SQLite + Postgres tests.

Subclasses provide a `self.adapter` fixture (pytest fixture name `adapter`).
"""

import pytest

from implementation.db.errors import ValidationError


class AdapterContract:
    # Subclasses override via a pytest fixture named `adapter` returning an instance.

    def test_list_tables(self, adapter):
        tables = set(adapter.list_tables())
        assert {"students", "courses", "enrollments"} <= tables

    def test_get_table_schema_students(self, adapter):
        cols = {c["name"] for c in adapter.get_table_schema("students")}
        assert cols == {"id", "name", "cohort", "score"}

    def test_get_full_schema_has_all_tables(self, adapter):
        full = adapter.get_full_schema()
        assert {"students", "courses", "enrollments"} <= set(full)
        assert any(c["name"] == "name" for c in full["students"])
```

- [ ] **Step 4: Write `tests/test_sqlite_adapter.py`**

```python
import pytest

from implementation.db.errors import ValidationError
from ._adapter_contract import AdapterContract


class TestSQLiteContract(AdapterContract):
    @pytest.fixture
    def adapter(self, sqlite_adapter):
        return sqlite_adapter
```

- [ ] **Step 5: Run tests, confirm they fail (no SQLiteAdapter yet)**

Run: `uv run pytest implementation/tests/test_sqlite_adapter.py -v`
Expected: ImportError on `SQLiteAdapter`.

- [ ] **Step 6: Implement `sqlite_adapter.py` (skeleton + list_tables + schema)**

```python
"""SQLite implementation of DatabaseAdapter."""

from __future__ import annotations

import sqlite3
from typing import Any

from .base import DatabaseAdapter
from .errors import AdapterError, ValidationError
from . import validators


class SQLiteAdapter(DatabaseAdapter):
    def __init__(self, path: str):
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")

    def close(self) -> None:
        self._conn.close()

    def list_tables(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return [r["name"] for r in rows]

    def get_table_schema(self, table: str) -> list[dict[str, Any]]:
        validators.validate_identifier(table)
        if table not in self.list_tables():
            raise ValidationError(f"unknown table: {table!r}")
        rows = self._conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        return [
            {
                "name": r["name"],
                "type": r["type"],
                "nullable": not bool(r["notnull"]),
                "primary_key": bool(r["pk"]),
                "default": r["dflt_value"],
            }
            for r in rows
        ]

    def get_full_schema(self) -> dict[str, list[dict[str, Any]]]:
        return {t: self.get_table_schema(t) for t in self.list_tables()}

    # Stubs — raise so test failures point at the missing method.
    def search(self, *a, **kw):
        raise NotImplementedError

    def insert(self, *a, **kw):
        raise NotImplementedError

    def aggregate(self, *a, **kw):
        raise NotImplementedError
```

- [ ] **Step 7: Run tests, expect contract tests to pass**

Run: `uv run pytest implementation/tests/test_sqlite_adapter.py -v`
Expected: 3 contract tests PASS.

---

## Task 6: SQLite Adapter — search (TDD)

**Files:**
- Modify: `implementation/db/sqlite_adapter.py`
- Modify: `implementation/tests/_adapter_contract.py`

- [ ] **Step 1: Add search tests to `_adapter_contract.py`**

Append to `AdapterContract`:

```python
    # --- search ---

    def test_search_returns_all_columns_by_default(self, adapter):
        result = adapter.search("students", limit=3)
        assert result["table"] == "students"
        assert set(result["columns"]) == {"id", "name", "cohort", "score"}
        assert len(result["rows"]) == 3
        assert result["limit"] == 3 and result["offset"] == 0

    def test_search_projects_columns(self, adapter):
        result = adapter.search("students", columns=["name", "cohort"], limit=1)
        assert set(result["rows"][0]) == {"name", "cohort"}

    def test_search_filter_equals(self, adapter):
        result = adapter.search(
            "students",
            filters=[{"column": "cohort", "op": "=", "value": "A1"}],
            limit=50,
        )
        assert all(r["cohort"] == "A1" for r in result["rows"])
        assert len(result["rows"]) == 4

    def test_search_filter_in(self, adapter):
        result = adapter.search(
            "students",
            filters=[{"column": "cohort", "op": "IN", "value": ["A1", "B2"]}],
            limit=50,
        )
        assert len(result["rows"]) == 10

    def test_search_filter_like(self, adapter):
        result = adapter.search(
            "students",
            filters=[{"column": "name", "op": "LIKE", "value": "A%"}],
        )
        assert all(r["name"].startswith("A") for r in result["rows"])

    def test_search_order_by_descending(self, adapter):
        result = adapter.search("students", order_by="score", descending=True, limit=3)
        scores = [r["score"] for r in result["rows"]]
        assert scores == sorted(scores, reverse=True)

    def test_search_pagination_has_more(self, adapter):
        page1 = adapter.search("students", limit=5, offset=0)
        page2 = adapter.search("students", limit=5, offset=5)
        assert page1["has_more"] is True
        assert page2["has_more"] in (False, True)
        ids = {r["id"] for r in page1["rows"]} | {r["id"] for r in page2["rows"]}
        assert len(ids) == 10

    def test_search_rejects_unknown_table(self, adapter):
        with pytest.raises(ValidationError):
            adapter.search("ghosts")

    def test_search_rejects_unknown_column(self, adapter):
        with pytest.raises(ValidationError):
            adapter.search("students", columns=["ghost"])

    def test_search_rejects_bad_operator(self, adapter):
        with pytest.raises(ValidationError):
            adapter.search("students", filters=[{"column": "id", "op": "OR", "value": 1}])

    def test_search_clamps_limit(self, adapter):
        # Adapter should clamp to [1, 200].
        result = adapter.search("students", limit=10_000)
        assert result["limit"] == 200
        result2 = adapter.search("students", limit=0)
        assert result2["limit"] == 1
```

- [ ] **Step 2: Run tests, expect failures**

Run: `uv run pytest implementation/tests/test_sqlite_adapter.py -v`
Expected: `NotImplementedError` on all new tests.

- [ ] **Step 3: Implement `search` in `sqlite_adapter.py`**

Replace the `search` stub:

```python
    def search(
        self,
        table: str,
        columns: list[str] | None = None,
        filters: list[dict] | None = None,
        order_by: str | None = None,
        descending: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        validators.validate_table(self, table)
        cols = validators.validate_columns(self, table, columns)
        fs = validators.validate_filters(self, table, filters)
        if order_by is not None:
            validators.validate_columns(self, table, [order_by])

        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))

        col_sql = ", ".join(f'"{c}"' for c in cols)
        sql = f'SELECT {col_sql} FROM "{table}"'
        params: list = []

        if fs:
            clauses = []
            for f in fs:
                col, op, val = f["column"], f["op"], f["value"]
                if op == "IN":
                    placeholders = ", ".join("?" for _ in val)
                    clauses.append(f'"{col}" IN ({placeholders})')
                    params.extend(val)
                else:
                    clauses.append(f'"{col}" {op} ?')
                    params.append(val)
            sql += " WHERE " + " AND ".join(clauses)

        if order_by is not None:
            direction = "DESC" if descending else "ASC"
            sql += f' ORDER BY "{order_by}" {direction}'

        sql += " LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        try:
            rows = self._conn.execute(sql, params).fetchall()
        except sqlite3.Error as e:
            raise AdapterError(str(e)) from e

        out = [dict(r) for r in rows]
        return {
            "table": table,
            "columns": cols,
            "rows": out,
            "count": len(out),
            "limit": limit,
            "offset": offset,
            "has_more": len(out) == limit,
        }
```

- [ ] **Step 4: Run tests, expect all green**

Run: `uv run pytest implementation/tests/test_sqlite_adapter.py -v`
Expected: all search tests PASS.

---

## Task 7: SQLite Adapter — insert (TDD)

**Files:**
- Modify: `implementation/db/sqlite_adapter.py`
- Modify: `implementation/tests/_adapter_contract.py`

- [ ] **Step 1: Add insert tests to `_adapter_contract.py`**

```python
    # --- insert ---

    def test_insert_returns_payload_with_id(self, adapter):
        result = adapter.insert("students", {"name": "Zen", "cohort": "A1", "score": 7.5})
        assert result["table"] == "students"
        assert result["inserted"]["name"] == "Zen"
        assert isinstance(result["id"], int) and result["id"] > 0

    def test_insert_is_visible_to_search(self, adapter):
        adapter.insert("students", {"name": "Mai", "cohort": "C3", "score": 8.0})
        found = adapter.search(
            "students",
            filters=[{"column": "cohort", "op": "=", "value": "C3"}],
        )
        assert any(r["name"] == "Mai" for r in found["rows"])

    def test_insert_rejects_empty(self, adapter):
        with pytest.raises(ValidationError):
            adapter.insert("students", {})

    def test_insert_rejects_unknown_column(self, adapter):
        with pytest.raises(ValidationError):
            adapter.insert("students", {"ghost": 1})

    def test_insert_rejects_unknown_table(self, adapter):
        with pytest.raises(ValidationError):
            adapter.insert("ghosts", {"x": 1})
```

- [ ] **Step 2: Run tests, expect failures**

Run: `uv run pytest implementation/tests/test_sqlite_adapter.py -k insert -v`
Expected: `NotImplementedError` on insert tests.

- [ ] **Step 3: Implement `insert`**

```python
    def insert(self, table: str, values: dict) -> dict:
        validators.validate_table(self, table)
        validators.validate_insert_values(self, table, values)

        cols = list(values)
        col_sql = ", ".join(f'"{c}"' for c in cols)
        placeholder_sql = ", ".join("?" for _ in cols)
        sql = f'INSERT INTO "{table}" ({col_sql}) VALUES ({placeholder_sql})'

        try:
            cur = self._conn.execute(sql, [values[c] for c in cols])
            self._conn.commit()
            new_id = cur.lastrowid
        except sqlite3.Error as e:
            raise AdapterError(str(e)) from e

        return {
            "table": table,
            "inserted": {**values, "id": new_id} if "id" not in values else dict(values),
            "id": new_id,
        }
```

- [ ] **Step 4: Run tests, expect all green**

Run: `uv run pytest implementation/tests/test_sqlite_adapter.py -v`
Expected: all PASS so far.

---

## Task 8: SQLite Adapter — aggregate (TDD)

**Files:**
- Modify: `implementation/db/sqlite_adapter.py`
- Modify: `implementation/tests/_adapter_contract.py`

- [ ] **Step 1: Add aggregate tests to `_adapter_contract.py`**

```python
    # --- aggregate ---

    def test_aggregate_count_all(self, adapter):
        result = adapter.aggregate("students", "count")
        assert result["metric"] == "count"
        assert result["rows"] == [{"group": None, "value": 10}]

    def test_aggregate_avg_score(self, adapter):
        result = adapter.aggregate("students", "avg", column="score")
        assert result["metric"] == "avg"
        assert len(result["rows"]) == 1
        assert 0 < result["rows"][0]["value"] < 10

    def test_aggregate_sum_min_max(self, adapter):
        for metric, expected_check in [
            ("sum", lambda v: v > 0),
            ("min", lambda v: v == 5.5),
            ("max", lambda v: v == 9.2),
        ]:
            result = adapter.aggregate("students", metric, column="score")
            assert expected_check(result["rows"][0]["value"]), (metric, result)

    def test_aggregate_group_by_cohort(self, adapter):
        result = adapter.aggregate("students", "avg", column="score", group_by="cohort")
        groups = {r["group"]: r["value"] for r in result["rows"]}
        assert set(groups) == {"A1", "B2"}

    def test_aggregate_count_with_filter(self, adapter):
        result = adapter.aggregate(
            "students", "count",
            filters=[{"column": "cohort", "op": "=", "value": "A1"}],
        )
        assert result["rows"][0]["value"] == 4

    def test_aggregate_rejects_unknown_metric(self, adapter):
        with pytest.raises(ValidationError):
            adapter.aggregate("students", "median", column="score")

    def test_aggregate_requires_column_for_avg(self, adapter):
        with pytest.raises(ValidationError):
            adapter.aggregate("students", "avg")

    def test_aggregate_rejects_unknown_column(self, adapter):
        with pytest.raises(ValidationError):
            adapter.aggregate("students", "avg", column="ghost")
```

- [ ] **Step 2: Run tests, expect failures**

Run: `uv run pytest implementation/tests/test_sqlite_adapter.py -k aggregate -v`
Expected: `NotImplementedError`.

- [ ] **Step 3: Implement `aggregate`**

```python
    def aggregate(
        self,
        table: str,
        metric: str,
        column: str | None = None,
        filters: list[dict] | None = None,
        group_by: str | None = None,
    ) -> dict:
        validators.validate_table(self, table)
        m = validators.validate_metric(metric)
        if m != "count" and column is None:
            raise ValidationError(f"metric {m!r} requires a column")
        if column is not None:
            validators.validate_columns(self, table, [column])
        if group_by is not None:
            validators.validate_columns(self, table, [group_by])
        fs = validators.validate_filters(self, table, filters)

        if m == "count" and column is None:
            select = "COUNT(*) AS value"
        else:
            select = f'{m.upper()}("{column}") AS value'

        if group_by is not None:
            sql = f'SELECT "{group_by}" AS grp, {select} FROM "{table}"'
        else:
            sql = f"SELECT {select} FROM \"{table}\""

        params: list = []
        if fs:
            clauses = []
            for f in fs:
                col, op, val = f["column"], f["op"], f["value"]
                if op == "IN":
                    placeholders = ", ".join("?" for _ in val)
                    clauses.append(f'"{col}" IN ({placeholders})')
                    params.extend(val)
                else:
                    clauses.append(f'"{col}" {op} ?')
                    params.append(val)
            sql += " WHERE " + " AND ".join(clauses)

        if group_by is not None:
            sql += f' GROUP BY "{group_by}"'

        try:
            rows = self._conn.execute(sql, params).fetchall()
        except sqlite3.Error as e:
            raise AdapterError(str(e)) from e

        if group_by is not None:
            out_rows = [{"group": r["grp"], "value": r["value"]} for r in rows]
        else:
            out_rows = [{"group": None, "value": rows[0]["value"] if rows else 0}]

        return {"table": table, "metric": m, "column": column, "rows": out_rows}
```

- [ ] **Step 4: Run all adapter tests**

Run: `uv run pytest implementation/tests/test_sqlite_adapter.py -v`
Expected: every test PASS (~30 tests).

---

## Task 9: MCP Server — Tools

**Files:**
- Create: `implementation/mcp_server.py` (initial)
- Create: `implementation/tests/test_tools.py`

- [ ] **Step 1: Write `tests/test_tools.py` (failing)**

```python
import pytest
from fastmcp import Client

from implementation.mcp_server import build_server
from implementation.db.sqlite_adapter import SQLiteAdapter


@pytest.fixture
def server(seeded_sqlite_path):
    adapter = SQLiteAdapter(str(seeded_sqlite_path))
    server = build_server(adapter)
    yield server
    adapter.close()


@pytest.fixture
async def client(server):
    async with Client(server) as c:
        yield c


class TestToolDiscovery:
    async def test_three_tools_exposed(self, client):
        tools = await client.list_tools()
        names = {t.name for t in tools}
        assert names == {"search", "insert", "aggregate"}


class TestSearchTool:
    async def test_happy(self, client):
        result = await client.call_tool(
            "search",
            {"table": "students", "filters": [{"column": "cohort", "op": "=", "value": "A1"}]},
        )
        # FastMCP returns structured content; access .data or .structured_content
        data = result.data if hasattr(result, "data") else result.structured_content
        assert data["table"] == "students"
        assert len(data["rows"]) == 4

    async def test_unknown_table_error(self, client):
        with pytest.raises(Exception) as exc:
            await client.call_tool("search", {"table": "ghosts"})
        assert "validation" in str(exc.value).lower()


class TestInsertTool:
    async def test_happy_and_visible_to_search(self, client):
        ins = await client.call_tool(
            "insert",
            {"table": "students", "values": {"name": "ToolUser", "cohort": "Z9", "score": 10.0}},
        )
        ins_data = ins.data if hasattr(ins, "data") else ins.structured_content
        assert ins_data["id"] > 0

        srch = await client.call_tool(
            "search",
            {"table": "students", "filters": [{"column": "cohort", "op": "=", "value": "Z9"}]},
        )
        data = srch.data if hasattr(srch, "data") else srch.structured_content
        assert any(r["name"] == "ToolUser" for r in data["rows"])

    async def test_empty_values_error(self, client):
        with pytest.raises(Exception) as exc:
            await client.call_tool("insert", {"table": "students", "values": {}})
        assert "validation" in str(exc.value).lower()


class TestAggregateTool:
    async def test_count_all(self, client):
        result = await client.call_tool("aggregate", {"table": "students", "metric": "count"})
        data = result.data if hasattr(result, "data") else result.structured_content
        assert data["rows"][0]["value"] >= 10

    async def test_avg_by_group(self, client):
        result = await client.call_tool(
            "aggregate",
            {"table": "students", "metric": "avg", "column": "score", "group_by": "cohort"},
        )
        data = result.data if hasattr(result, "data") else result.structured_content
        groups = {r["group"] for r in data["rows"]}
        assert {"A1", "B2"} <= groups

    async def test_invalid_metric_error(self, client):
        with pytest.raises(Exception) as exc:
            await client.call_tool(
                "aggregate", {"table": "students", "metric": "median", "column": "score"}
            )
        assert "validation" in str(exc.value).lower()
```

- [ ] **Step 2: Run tests, expect ImportError**

Run: `uv run pytest implementation/tests/test_tools.py -v`
Expected: ImportError on `build_server`.

- [ ] **Step 3: Verify FastMCP tool/error API via context7 (optional but recommended)**

Spawn a quick research check if unsure of current FastMCP names. The plan below uses the public surface as of FastMCP 2.x: `FastMCP(name)`, `@mcp.tool(name=...)`, `@mcp.resource(uri)`, `mcp.run(transport=...)`, raise `fastmcp.exceptions.ToolError` to surface user-facing errors. If a name has drifted, adjust the imports — behaviour stays the same.

- [ ] **Step 4: Write `mcp_server.py` (tools only — resources come next)**

```python
"""FastMCP entrypoint. SQL stays out of this module by design."""

from __future__ import annotations

import argparse
import functools
import os
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError

from .db.base import DatabaseAdapter
from .db.errors import AdapterError, ValidationError
from .db.sqlite_adapter import SQLiteAdapter


def _to_tool_error(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except ValidationError as e:
            raise ToolError(f"validation: {e}") from e
        except AdapterError as e:
            raise ToolError(f"database: {e}") from e
    return wrapper


def build_server(adapter: DatabaseAdapter) -> FastMCP:
    mcp = FastMCP("SQLite Lab MCP Server")

    @mcp.tool(name="search")
    @_to_tool_error
    def search(
        table: str,
        columns: list[str] | None = None,
        filters: list[dict] | None = None,
        order_by: str | None = None,
        descending: bool = False,
        limit: int = 20,
        offset: int = 0,
    ) -> dict:
        """Search rows from a table with optional filters, projection, ordering, pagination."""
        return adapter.search(
            table=table,
            columns=columns,
            filters=filters,
            order_by=order_by,
            descending=descending,
            limit=limit,
            offset=offset,
        )

    @mcp.tool(name="insert")
    @_to_tool_error
    def insert(table: str, values: dict) -> dict:
        """Insert a row into a table. Returns the inserted payload and id."""
        return adapter.insert(table=table, values=values)

    @mcp.tool(name="aggregate")
    @_to_tool_error
    def aggregate(
        table: str,
        metric: str,
        column: str | None = None,
        filters: list[dict] | None = None,
        group_by: str | None = None,
    ) -> dict:
        """Compute count/avg/sum/min/max, optionally grouped."""
        return adapter.aggregate(
            table=table, metric=metric, column=column, filters=filters, group_by=group_by
        )

    return mcp


def _make_adapter() -> DatabaseAdapter:
    backend = os.getenv("DB_BACKEND", "sqlite").lower()
    if backend == "sqlite":
        return SQLiteAdapter(os.getenv("SQLITE_PATH", "lab.db"))
    if backend == "postgres":
        from .db.postgres_adapter import PostgresAdapter  # imported lazily
        dsn = os.getenv("PG_DSN", "postgresql://lab:lab@localhost:55432/lab")
        return PostgresAdapter(dsn)
    raise SystemExit(f"unknown DB_BACKEND={backend!r}; use 'sqlite' or 'postgres'")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "http"], default="stdio")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    adapter = _make_adapter()
    mcp = build_server(adapter)

    if args.transport == "http":
        from .auth import attach_bearer_auth  # lazy: only needed for HTTP
        attach_bearer_auth(mcp)
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        mcp.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tool tests**

Run: `uv run pytest implementation/tests/test_tools.py -v`
Expected: all PASS. If a test fails on `result.data` vs `result.structured_content`, that's a FastMCP API shape: the test already tries both, so an assert failure is a real bug, not API drift.

---

## Task 10: MCP Server — Resources

**Files:**
- Modify: `implementation/mcp_server.py`
- Create: `implementation/tests/test_resources.py`

- [ ] **Step 1: Write `test_resources.py` (failing)**

```python
import json
import pytest
from fastmcp import Client

from implementation.mcp_server import build_server
from implementation.db.sqlite_adapter import SQLiteAdapter


@pytest.fixture
def server(seeded_sqlite_path):
    adapter = SQLiteAdapter(str(seeded_sqlite_path))
    yield build_server(adapter)
    adapter.close()


@pytest.fixture
async def client(server):
    async with Client(server) as c:
        yield c


async def _read_text(client, uri: str) -> str:
    res = await client.read_resource(uri)
    # FastMCP returns a list of TextResourceContents
    return res[0].text if isinstance(res, list) else res.contents[0].text


class TestResourceDiscovery:
    async def test_database_resource_listed(self, client):
        resources = await client.list_resources()
        uris = {str(r.uri) for r in resources}
        assert "schema://database" in uris

    async def test_table_template_listed(self, client):
        templates = await client.list_resource_templates()
        uris = {str(t.uriTemplate) for t in templates}
        assert "schema://table/{table_name}" in uris


class TestReadResources:
    async def test_full_schema(self, client):
        text = await _read_text(client, "schema://database")
        data = json.loads(text)
        assert "tables" in data
        assert {"students", "courses", "enrollments"} <= set(data["tables"])

    async def test_single_table_schema(self, client):
        text = await _read_text(client, "schema://table/students")
        data = json.loads(text)
        assert data["table"] == "students"
        names = {c["name"] for c in data["columns"]}
        assert names == {"id", "name", "cohort", "score"}

    async def test_unknown_table_errors(self, client):
        with pytest.raises(Exception):
            await _read_text(client, "schema://table/ghosts")
```

- [ ] **Step 2: Run tests, expect failures**

Run: `uv run pytest implementation/tests/test_resources.py -v`
Expected: fails — resources not declared.

- [ ] **Step 3: Add resources to `build_server` in `mcp_server.py`**

Inside `build_server`, before `return mcp`:

```python
    import json as _json

    @mcp.resource("schema://database", mime_type="application/json")
    def database_schema() -> str:
        """Full database schema as JSON text."""
        return _json.dumps({"tables": adapter.get_full_schema()}, default=str, indent=2)

    @mcp.resource("schema://table/{table_name}", mime_type="application/json")
    def table_schema(table_name: str) -> str:
        """Single table schema as JSON text."""
        try:
            cols = adapter.get_table_schema(table_name)
        except ValidationError as e:
            raise ToolError(f"validation: {e}") from e
        return _json.dumps({"table": table_name, "columns": cols}, default=str, indent=2)
```

- [ ] **Step 4: Run resource tests, expect green**

Run: `uv run pytest implementation/tests/test_resources.py -v`
Expected: all PASS.

---

## Task 11: Bearer Auth Middleware

**Files:**
- Create: `implementation/auth.py`
- Create: `implementation/tests/test_auth.py`

- [ ] **Step 1: Write `tests/test_auth.py` (failing)**

```python
import asyncio
import os
import socket

import httpx
import pytest

from implementation.db.sqlite_adapter import SQLiteAdapter
from implementation.mcp_server import build_server
from implementation.auth import attach_bearer_auth


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def http_server(seeded_sqlite_path, monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "test-token-123")
    adapter = SQLiteAdapter(str(seeded_sqlite_path))
    mcp = build_server(adapter)
    attach_bearer_auth(mcp)

    port = _free_port()
    # FastMCP HTTP runs as an asyncio task
    task = asyncio.create_task(mcp.run_http_async(host="127.0.0.1", port=port))
    # Wait until the port responds
    for _ in range(40):
        try:
            async with httpx.AsyncClient() as c:
                await c.get(f"http://127.0.0.1:{port}/")
            break
        except Exception:
            await asyncio.sleep(0.05)
    yield port
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    adapter.close()


@pytest.fixture
def env_no_token(monkeypatch):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)


class TestAuthStartup:
    def test_missing_env_token_refuses_to_start(self, env_no_token):
        adapter_path = ":memory:"
        adapter = SQLiteAdapter(adapter_path)
        mcp = build_server(adapter)
        with pytest.raises(RuntimeError, match="MCP_AUTH_TOKEN"):
            attach_bearer_auth(mcp)
        adapter.close()


class TestAuthRequests:
    async def test_missing_header_returns_401(self, http_server):
        port = http_server
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"http://127.0.0.1:{port}/mcp",
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
            )
        assert r.status_code == 401
        assert r.json()["error"] == "unauthorized"

    async def test_bad_token_returns_401(self, http_server):
        port = http_server
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"http://127.0.0.1:{port}/mcp",
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
                headers={"Authorization": "Bearer wrong"},
            )
        assert r.status_code == 401

    async def test_valid_token_returns_200(self, http_server):
        port = http_server
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"http://127.0.0.1:{port}/mcp",
                json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
                headers={
                    "Authorization": "Bearer test-token-123",
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                },
            )
        assert r.status_code == 200
```

- [ ] **Step 2: Run tests, expect ImportError**

Run: `uv run pytest implementation/tests/test_auth.py -v`
Expected: ImportError on `attach_bearer_auth`.

- [ ] **Step 3: Implement `auth.py`**

```python
"""Bearer-token auth for HTTP transport.

Bound to FastMCP via a Starlette middleware wrapping the ASGI app, which
is the most stable extension point across FastMCP 2.x versions. If a
future FastMCP version exposes a first-class middleware hook with the
same semantics, the entry point `attach_bearer_auth` can be reimplemented
to use it — callers do not change.
"""

from __future__ import annotations

import hmac
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class BearerAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, expected_token: str):
        super().__init__(app)
        self._expected = expected_token.encode()

    async def dispatch(self, request, call_next):
        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return _unauthorized("missing bearer token")
        presented = auth.split(" ", 1)[1].strip().encode()
        if not hmac.compare_digest(presented, self._expected):
            return _unauthorized("invalid token")
        return await call_next(request)


def _unauthorized(reason: str) -> JSONResponse:
    return JSONResponse(
        {"error": "unauthorized", "reason": reason},
        status_code=401,
        headers={"WWW-Authenticate": 'Bearer realm="mcp"'},
    )


def attach_bearer_auth(mcp) -> None:
    """Wrap the FastMCP HTTP app with Bearer-token enforcement.

    Reads MCP_AUTH_TOKEN at attach time. Raises RuntimeError if unset, so
    starting the HTTP transport without a token is impossible.
    """
    token = os.environ.get("MCP_AUTH_TOKEN", "").strip()
    if not token:
        raise RuntimeError("MCP_AUTH_TOKEN must be set when HTTP transport is enabled")
    # FastMCP exposes `http_app()` returning the underlying Starlette/FastAPI app
    # in 2.x; alternatively `custom_route`/`add_middleware`. We attach via
    # add_middleware on the mcp object so transport setup picks it up.
    mcp.add_middleware(BearerAuthMiddleware, expected_token=token)
```

> **Note for the implementer:** the line `mcp.add_middleware(BearerAuthMiddleware, expected_token=token)` assumes FastMCP exposes `add_middleware` with Starlette semantics. If the installed FastMCP version uses a different attachment style (e.g., `mcp.http_app().add_middleware(...)`), call that instead — the behaviour test still passes either way. Verify by running `python -c "from fastmcp import FastMCP; print([a for a in dir(FastMCP) if 'middleware' in a.lower() or 'http' in a.lower()])"` if needed.

- [ ] **Step 4: Run tests, expect green**

Run: `uv run pytest implementation/tests/test_auth.py -v`
Expected: all PASS. If `run_http_async` is not the exact method name in your FastMCP version, swap to whatever async runner FastMCP exposes (e.g., `run_async(transport="http", ...)`). Behaviour assertions remain identical.

---

## Task 12: Postgres Adapter (Bonus)

**Files:**
- Create: `docker/docker-compose.yml`
- Create: `docker/init.sql`
- Create: `implementation/db/postgres_adapter.py`
- Create: `implementation/tests/test_postgres_adapter.py`
- Create: `scripts/teardown.sh`

- [ ] **Step 1: Create `docker/init.sql`**

```sql
CREATE TABLE IF NOT EXISTS students (
    id     SERIAL PRIMARY KEY,
    name   TEXT    NOT NULL,
    cohort TEXT    NOT NULL,
    score  REAL    NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS courses (
    id      SERIAL PRIMARY KEY,
    title   TEXT    NOT NULL,
    credits INTEGER NOT NULL DEFAULT 3
);

CREATE TABLE IF NOT EXISTS enrollments (
    id         SERIAL PRIMARY KEY,
    student_id INTEGER NOT NULL REFERENCES students(id),
    course_id  INTEGER NOT NULL REFERENCES courses(id),
    grade      REAL
);

INSERT INTO students (name, cohort, score) VALUES
    ('Anh', 'A1', 8.5),
    ('Binh', 'A1', 7.0),
    ('Cuc', 'A1', 9.2),
    ('Dung', 'A1', 6.5),
    ('Em', 'B2', 8.8),
    ('Phong', 'B2', 7.4),
    ('Giang', 'B2', 9.0),
    ('Hoa', 'B2', 5.5),
    ('Khanh', 'B2', 8.0),
    ('Linh', 'B2', 6.8);

INSERT INTO courses (title, credits) VALUES
    ('Algorithms', 4),
    ('Databases', 3),
    ('Operating Systems', 4),
    ('Distributed Systems', 3);

INSERT INTO enrollments (student_id, course_id, grade) VALUES
    (1, 1, 8.0), (1, 2, 9.0), (2, 1, 7.5), (3, 2, 9.5),
    (3, 3, 8.5), (4, 4, 6.0), (5, 1, 9.0), (5, 3, 8.0),
    (6, 2, 7.0), (7, 4, 9.5), (8, 1, 5.5), (8, 4, 6.0),
    (9, 2, 8.5), (10, 3, 7.0), (10, 4, 6.5);
```

- [ ] **Step 2: Create `docker/docker-compose.yml`**

```yaml
name: mcp-sqlite-lab

services:
  postgres:
    image: postgres:16-alpine
    container_name: mcp-sqlite-lab-postgres
    environment:
      POSTGRES_USER: lab
      POSTGRES_PASSWORD: lab
      POSTGRES_DB: lab
    ports:
      - "55432:5432"
    volumes:
      - mcp-lab-data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U lab -d lab"]
      interval: 2s
      timeout: 3s
      retries: 10

volumes:
  mcp-lab-data:
```

- [ ] **Step 3: Create `scripts/teardown.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../docker"
docker compose -p mcp-sqlite-lab down -v --remove-orphans
echo "✓ Removed mcp-sqlite-lab containers, network, and volumes."
```

Make executable: `chmod +x scripts/teardown.sh`

- [ ] **Step 4: Start Postgres**

Run: `docker compose -f docker/docker-compose.yml -p mcp-sqlite-lab up -d`
Then: `docker compose -p mcp-sqlite-lab ps`
Expected: `mcp-sqlite-lab-postgres` is `(healthy)`.

- [ ] **Step 5: Implement `postgres_adapter.py`**

```python
"""PostgreSQL implementation of DatabaseAdapter."""

from __future__ import annotations

from typing import Any

import psycopg
from psycopg import sql

from .base import DatabaseAdapter
from .errors import AdapterError, ValidationError
from . import validators


class PostgresAdapter(DatabaseAdapter):
    def __init__(self, dsn: str):
        try:
            self._conn = psycopg.connect(dsn, autocommit=False)
        except psycopg.Error as e:
            raise AdapterError(f"connect failed: {e}") from e

    def close(self) -> None:
        self._conn.close()

    def list_tables(self) -> list[str]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename"
            )
            return [r[0] for r in cur.fetchall()]

    def get_table_schema(self, table: str) -> list[dict[str, Any]]:
        validators.validate_identifier(table)
        if table not in self.list_tables():
            raise ValidationError(f"unknown table: {table!r}")
        with self._conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    c.column_name,
                    c.data_type,
                    c.is_nullable,
                    c.column_default,
                    EXISTS(
                        SELECT 1 FROM information_schema.table_constraints tc
                        JOIN information_schema.key_column_usage k
                          ON k.constraint_name = tc.constraint_name
                        WHERE tc.constraint_type='PRIMARY KEY'
                          AND tc.table_name = c.table_name
                          AND k.column_name = c.column_name
                    ) AS is_pk
                FROM information_schema.columns c
                WHERE c.table_schema='public' AND c.table_name=%s
                ORDER BY c.ordinal_position
                """,
                (table,),
            )
            return [
                {
                    "name": r[0],
                    "type": r[1],
                    "nullable": r[2] == "YES",
                    "primary_key": bool(r[4]),
                    "default": r[3],
                }
                for r in cur.fetchall()
            ]

    def get_full_schema(self) -> dict[str, list[dict[str, Any]]]:
        return {t: self.get_table_schema(t) for t in self.list_tables()}

    # ---- internal SQL builders ----

    def _ident(self, name: str) -> sql.Identifier:
        return sql.Identifier(name)

    def _build_where(self, fs: list[dict]) -> tuple[sql.Composed | sql.SQL, list]:
        if not fs:
            return sql.SQL(""), []
        parts = []
        params: list = []
        for f in fs:
            col, op, val = f["column"], f["op"], f["value"]
            if op == "IN":
                placeholders = sql.SQL(", ").join(sql.Placeholder() * len(val))
                parts.append(sql.SQL("{c} IN ({ph})").format(c=self._ident(col), ph=placeholders))
                params.extend(val)
            else:
                parts.append(sql.SQL("{c} " + op + " %s").format(c=self._ident(col)))
                params.append(val)
        return sql.SQL(" WHERE ") + sql.SQL(" AND ").join(parts), params

    # ---- public methods ----

    def search(
        self, table, columns=None, filters=None,
        order_by=None, descending=False, limit=20, offset=0,
    ):
        validators.validate_table(self, table)
        cols = validators.validate_columns(self, table, columns)
        fs = validators.validate_filters(self, table, filters)
        if order_by is not None:
            validators.validate_columns(self, table, [order_by])
        limit = max(1, min(int(limit), 200))
        offset = max(0, int(offset))

        select_cols = sql.SQL(", ").join(self._ident(c) for c in cols)
        stmt = sql.SQL("SELECT {cs} FROM {t}").format(cs=select_cols, t=self._ident(table))
        where, params = self._build_where(fs)
        stmt = stmt + where
        if order_by is not None:
            stmt = stmt + sql.SQL(" ORDER BY {o} ").format(o=self._ident(order_by)) + sql.SQL(
                "DESC" if descending else "ASC"
            )
        stmt = stmt + sql.SQL(" LIMIT %s OFFSET %s")
        params.extend([limit, offset])

        try:
            with self._conn.cursor() as cur:
                cur.execute(stmt, params)
                rows = cur.fetchall()
                colnames = [d.name for d in cur.description]
        except psycopg.Error as e:
            self._conn.rollback()
            raise AdapterError(str(e)) from e

        out = [dict(zip(colnames, r)) for r in rows]
        return {
            "table": table, "columns": cols, "rows": out, "count": len(out),
            "limit": limit, "offset": offset, "has_more": len(out) == limit,
        }

    def insert(self, table, values):
        validators.validate_table(self, table)
        validators.validate_insert_values(self, table, values)
        cols = list(values)
        stmt = sql.SQL("INSERT INTO {t} ({cs}) VALUES ({ph}) RETURNING id").format(
            t=self._ident(table),
            cs=sql.SQL(", ").join(self._ident(c) for c in cols),
            ph=sql.SQL(", ").join(sql.Placeholder() * len(cols)),
        )
        try:
            with self._conn.cursor() as cur:
                cur.execute(stmt, [values[c] for c in cols])
                new_id = cur.fetchone()[0]
            self._conn.commit()
        except psycopg.Error as e:
            self._conn.rollback()
            raise AdapterError(str(e)) from e
        return {"table": table, "inserted": {**values, "id": new_id}, "id": new_id}

    def aggregate(self, table, metric, column=None, filters=None, group_by=None):
        validators.validate_table(self, table)
        m = validators.validate_metric(metric)
        if m != "count" and column is None:
            raise ValidationError(f"metric {m!r} requires a column")
        if column is not None:
            validators.validate_columns(self, table, [column])
        if group_by is not None:
            validators.validate_columns(self, table, [group_by])
        fs = validators.validate_filters(self, table, filters)

        if m == "count" and column is None:
            select = sql.SQL("COUNT(*) AS value")
        else:
            select = sql.SQL("{f}({c}) AS value").format(
                f=sql.SQL(m.upper()), c=self._ident(column)
            )
        if group_by is not None:
            stmt = sql.SQL("SELECT {g} AS grp, {s} FROM {t}").format(
                g=self._ident(group_by), s=select, t=self._ident(table)
            )
        else:
            stmt = sql.SQL("SELECT {s} FROM {t}").format(s=select, t=self._ident(table))
        where, params = self._build_where(fs)
        stmt = stmt + where
        if group_by is not None:
            stmt = stmt + sql.SQL(" GROUP BY {g}").format(g=self._ident(group_by))

        try:
            with self._conn.cursor() as cur:
                cur.execute(stmt, params)
                rows = cur.fetchall()
        except psycopg.Error as e:
            self._conn.rollback()
            raise AdapterError(str(e)) from e

        if group_by is not None:
            out_rows = [{"group": r[0], "value": r[1]} for r in rows]
        else:
            out_rows = [{"group": None, "value": rows[0][0] if rows else 0}]
        return {"table": table, "metric": m, "column": column, "rows": out_rows}
```

- [ ] **Step 6: Write `tests/test_postgres_adapter.py`**

```python
import os
import pytest

from implementation.db.postgres_adapter import PostgresAdapter
from ._adapter_contract import AdapterContract

PG_DSN = os.getenv("PG_DSN")

pytestmark = pytest.mark.skipif(
    PG_DSN is None,
    reason="Set PG_DSN to run Postgres adapter tests (e.g., docker compose up)",
)


@pytest.fixture
def adapter():
    a = PostgresAdapter(PG_DSN)  # type: ignore[arg-type]
    yield a
    a.close()


class TestPostgresContract(AdapterContract):
    pass
```

- [ ] **Step 7: Run Postgres tests**

Run: `PG_DSN="postgresql://lab:lab@localhost:55432/lab" uv run pytest implementation/tests/test_postgres_adapter.py -v`
Expected: same ~30 contract tests PASS.

If they fail because Postgres has data the test re-inserts (e.g. a `(name, cohort)` UNIQUE that the SQLite seed doesn't have), inspect — `init.sql` should match the SQLite seed exactly, and the contract tests insert rows with new cohorts that do not collide.

- [ ] **Step 8: Confirm test suite still skips when Postgres is down**

Stop Postgres: `docker compose -p mcp-sqlite-lab down`
Run: `uv run pytest implementation/tests/test_postgres_adapter.py -v`
Expected: tests are SKIPPED (because `PG_DSN` env is unset or pointing nowhere — the env-based skipif handles both).

Restart for the rest of the plan: `docker compose -f docker/docker-compose.yml -p mcp-sqlite-lab up -d`

---

## Task 13: verify_server.py (E2E Smoke)

**Files:**
- Create: `implementation/verify_server.py`

- [ ] **Step 1: Write `verify_server.py`**

```python
#!/usr/bin/env python
"""End-to-end smoke test. Prints PASS/FAIL per check; exits 0 iff all pass."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from fastmcp import Client

from implementation import init_db
from implementation.db.sqlite_adapter import SQLiteAdapter
from implementation.mcp_server import build_server


class Reporter:
    def __init__(self):
        self.passed = 0
        self.failed = 0

    def check(self, label: str, ok: bool, detail: str = ""):
        tag = "PASS" if ok else "FAIL"
        if ok:
            self.passed += 1
        else:
            self.failed += 1
        suffix = f" — {detail}" if detail else ""
        print(f"[{tag}] {label}{suffix}")


async def run_stdio_checks(seed_path: Path) -> Reporter:
    r = Reporter()
    adapter = SQLiteAdapter(str(seed_path))
    server = build_server(adapter)
    try:
        async with Client(server) as c:
            tools = await c.list_tools()
            r.check("server starts and lists tools", True)
            names = {t.name for t in tools}
            r.check("tools/list returns search, insert, aggregate",
                    {"search", "insert", "aggregate"} <= names,
                    f"got {sorted(names)}")

            resources = await c.list_resources()
            r.check("resources/list returns schema://database",
                    any(str(x.uri) == "schema://database" for x in resources))

            templates = await c.list_resource_templates()
            r.check("resources/templates/list returns schema://table/{table_name}",
                    any(str(t.uriTemplate) == "schema://table/{table_name}" for t in templates))

            # search valid
            res = await c.call_tool(
                "search",
                {"table": "students", "filters": [{"column": "cohort", "op": "=", "value": "A1"}]},
            )
            data = res.data if hasattr(res, "data") else res.structured_content
            r.check("search valid: returns rows", len(data["rows"]) > 0)

            # search invalid table
            try:
                await c.call_tool("search", {"table": "ghosts"})
                r.check("search invalid table: returns error", False, "no error raised")
            except Exception as e:
                r.check("search invalid table: returns error", "validation" in str(e).lower())

            # insert valid
            res = await c.call_tool(
                "insert",
                {"table": "students", "values": {"name": "Verify", "cohort": "Z9", "score": 7.0}},
            )
            data = res.data if hasattr(res, "data") else res.structured_content
            r.check("insert valid: returns inserted payload", data.get("id", 0) > 0)

            # insert empty
            try:
                await c.call_tool("insert", {"table": "students", "values": {}})
                r.check("insert empty: returns error", False, "no error raised")
            except Exception as e:
                r.check("insert empty: returns error", "validation" in str(e).lower())

            # aggregate count
            res = await c.call_tool("aggregate", {"table": "students", "metric": "count"})
            data = res.data if hasattr(res, "data") else res.structured_content
            r.check("aggregate count: returns number", data["rows"][0]["value"] >= 10)

            # aggregate avg by group
            res = await c.call_tool(
                "aggregate",
                {"table": "students", "metric": "avg", "column": "score", "group_by": "cohort"},
            )
            data = res.data if hasattr(res, "data") else res.structured_content
            r.check("aggregate avg by group: returns grouped rows",
                    len(data["rows"]) >= 2)

            # aggregate invalid metric
            try:
                await c.call_tool(
                    "aggregate",
                    {"table": "students", "metric": "median", "column": "score"},
                )
                r.check("aggregate invalid metric: returns error", False)
            except Exception as e:
                r.check("aggregate invalid metric: returns error",
                        "validation" in str(e).lower())

            # resource: schema://database
            res = await c.read_resource("schema://database")
            txt = res[0].text if isinstance(res, list) else res.contents[0].text
            parsed = json.loads(txt)
            r.check("resource schema://database: JSON parses with tables key",
                    "tables" in parsed)

            # resource: schema://table/students
            res = await c.read_resource("schema://table/students")
            txt = res[0].text if isinstance(res, list) else res.contents[0].text
            parsed = json.loads(txt)
            r.check("resource schema://table/students: parses, has columns",
                    parsed.get("table") == "students" and len(parsed.get("columns", [])) > 0)

            # resource: schema://table/missing
            try:
                await c.read_resource("schema://table/ghosts")
                r.check("resource schema://table/missing: returns error", False)
            except Exception:
                r.check("resource schema://table/missing: returns error", True)
    finally:
        adapter.close()
    return r


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="lab.db", help="SQLite path (will be re-seeded)")
    args = parser.parse_args()

    db_path = Path(args.db)
    if db_path.exists():
        db_path.unlink()
    init_db.create_schema(db_path)
    init_db.seed(db_path)

    reporter = asyncio.run(run_stdio_checks(db_path))
    print(f"\nSummary: {reporter.passed} passed, {reporter.failed} failed")
    sys.exit(0 if reporter.failed == 0 else 1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the verify script**

Run: `uv run python implementation/verify_server.py`
Expected: 14 `[PASS]` lines, `Summary: 14 passed, 0 failed`, exit code 0.

If any FAIL, fix the underlying tool/resource code and re-run.

---

## Task 14: Inspector Helper Script

**Files:**
- Create: `scripts/run-inspector.sh`

- [ ] **Step 1: Write `scripts/run-inspector.sh`**

```bash
#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Make sure deps are installed and resolve an absolute python path.
uv sync --quiet
PYTHON="$(uv run python -c 'import sys; print(sys.executable)')"

# Initialize the seed DB if it does not exist yet.
[ -f "$ROOT/lab.db" ] || uv run python implementation/init_db.py

NPM_CONFIG_CACHE="$ROOT/.npm-cache" npx -y @modelcontextprotocol/inspector \
    "$PYTHON" "$ROOT/implementation/mcp_server.py"
```

- [ ] **Step 2: Make executable**

Run: `chmod +x scripts/run-inspector.sh`

- [ ] **Step 3: Smoke test (manual)**

Run: `bash scripts/run-inspector.sh`
Expected: a local URL is printed; opening it in a browser shows the 3 tools and the schema resources. Press Ctrl-C to stop.

This step is interactive — for non-interactive verification, the pytest + verify_server suite already covers tool discovery.

---

## Task 15: Client Configs and README

**Files:**
- Create: `.mcp.json`
- Modify: `README.md`

- [ ] **Step 1: Create `.mcp.json` template**

```json
{
  "mcpServers": {
    "sqlite-lab": {
      "command": "/ABSOLUTE/PATH/TO/uv",
      "args": [
        "run",
        "--directory",
        "/ABSOLUTE/PATH/TO/REPO",
        "python",
        "implementation/mcp_server.py"
      ],
      "env": {
        "DB_BACKEND": "sqlite",
        "SQLITE_PATH": "lab.db"
      }
    }
  }
}
```

- [ ] **Step 2: Rewrite `README.md`**

Replace the existing `README.md` content with a setup + usage version. The original lab spec is preserved as `docs/lab-spec.md` for grading reference.

Run first: `git mv README.md docs/lab-spec.md` (preserves history)
Then create the new `README.md`:

```markdown
# Day 26 / Track 3 — FastMCP SQLite Lab

A FastMCP server that exposes a small SQLite database (students/courses/enrollments) through MCP tools and resources. Includes a Postgres adapter and Bearer-auth HTTP transport as bonus features.

Lab spec and grading rubric: see [`docs/lab-spec.md`](docs/lab-spec.md) and [`Rubric.md`](Rubric.md).
Design doc: [`docs/superpowers/specs/2026-05-14-mcp-sqlite-lab-design.md`](docs/superpowers/specs/2026-05-14-mcp-sqlite-lab-design.md).

## Setup

```bash
# 1. Install deps (creates .venv)
uv sync --extra dev --extra postgres

# 2. Initialize the SQLite database
uv run python implementation/init_db.py

# 3. Run all tests
uv run pytest -v

# 4. Run the end-to-end smoke test
uv run python implementation/verify_server.py
# Expected: Summary: 14 passed, 0 failed
```

## Running the server

```bash
# Stdio (default — for use with Claude Code, Codex, Gemini CLI, Inspector)
uv run python implementation/mcp_server.py

# HTTP with Bearer auth
export MCP_AUTH_TOKEN="dev-secret-token"
uv run python implementation/mcp_server.py --transport http --port 8765
```

## Tools

- `search(table, columns?, filters?, order_by?, descending?, limit=20, offset=0)`
- `insert(table, values)`
- `aggregate(table, metric, column?, filters?, group_by?)` — metrics: `count`, `avg`, `sum`, `min`, `max`

Supported filter operators: `=`, `!=`, `<`, `<=`, `>`, `>=`, `LIKE`, `IN`.

## Resources

- `schema://database` — full schema as JSON
- `schema://table/{table_name}` — single-table schema as JSON

## Client integrations

### MCP Inspector

```bash
bash scripts/run-inspector.sh
```
Opens Inspector with absolute paths to `python` and `mcp_server.py`. Uses a local `.npm-cache` so global npm is not touched.

### Claude Code

Edit `.mcp.json` in this directory: replace both `/ABSOLUTE/PATH/TO/uv` and `/ABSOLUTE/PATH/TO/REPO` with the outputs of `which uv` and `pwd`. Then launch Claude Code in this directory.

### Gemini CLI

```bash
gemini mcp add sqlitelab "$(which uv)" run --directory "$PWD" python implementation/mcp_server.py \
    --description "SQLite lab FastMCP server" --timeout 10000
gemini mcp list

# Smoke test, headless
gemini --allowed-mcp-server-names sqlitelab --yolo -p \
    "List the available tools and run search on students with cohort A1."
```

Alias `sqlitelab` deliberately has no underscore — Gemini CLI does not accept underscores in MCP aliases.

### HTTP / curl (auth demo)

```bash
# Missing token -> 401
curl -sS -X POST http://127.0.0.1:8765/mcp \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'

# Valid token -> 200
curl -sS -X POST http://127.0.0.1:8765/mcp \
    -H "Authorization: Bearer dev-secret-token" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

## Postgres backend (bonus)

Postgres runs in Docker, fully isolated under project name `mcp-sqlite-lab`. **This setup does not touch any other Docker resource on your machine.**

```bash
# Start Postgres on port 55432 (not 5432, to avoid clashing with any existing instance)
docker compose -f docker/docker-compose.yml -p mcp-sqlite-lab up -d

# Run the server against Postgres
DB_BACKEND=postgres \
PG_DSN="postgresql://lab:lab@localhost:55432/lab" \
    uv run python implementation/mcp_server.py

# Same verify script, against Postgres
DB_BACKEND=postgres \
PG_DSN="postgresql://lab:lab@localhost:55432/lab" \
    uv run python implementation/verify_server.py

# Same pytest suite, with Postgres tests active
PG_DSN="postgresql://lab:lab@localhost:55432/lab" uv run pytest -v
```

### Teardown — remove all `mcp-sqlite-lab` Docker resources

```bash
bash scripts/teardown.sh
```

This runs `docker compose -p mcp-sqlite-lab down -v --remove-orphans`, which only removes containers, networks, and volumes prefixed `mcp-sqlite-lab`. Other containers and volumes on your machine are not affected.

## Project layout

```
implementation/
  mcp_server.py        FastMCP entrypoint (tools + resources)
  init_db.py           SQLite schema + seed
  verify_server.py     E2E smoke test
  auth.py              Bearer-token middleware for HTTP transport
  db/
    base.py            DatabaseAdapter ABC
    sqlite_adapter.py
    postgres_adapter.py
    validators.py      identifier + operator + metric whitelist
    errors.py
  tests/               pytest suite
docker/                isolated Postgres compose
scripts/               teardown.sh, run-inspector.sh
docs/
  lab-spec.md          original lab brief
  superpowers/         design and implementation plan
```

## Demo video shots (~2 minutes)

1. `uv run pytest` green.
2. `uv run python implementation/verify_server.py` showing 14 PASS.
3. Inspector showing the 3 tools and 2 resources.
4. Gemini CLI headless run, returning real data.
5. HTTP transport: the two `curl` calls (401 then 200).
6. `docker compose up` + `verify_server.py` against Postgres, same 14 PASS.
7. `bash scripts/teardown.sh` removing everything.
```

- [ ] **Step 3: Verify README renders**

Run: `head -40 README.md`
Expected: markdown header, setup section visible. Optional: paste into a Markdown previewer if available.

---

## Task 16: Final Verification and Commit

**Files:**
- None changed; runs the full suite and commits.

- [ ] **Step 1: Run the full pytest suite (SQLite only)**

Run: `uv run pytest -v`
Expected: all SQLite tests PASS, Postgres tests SKIPPED, auth tests PASS.

- [ ] **Step 2: Run the suite with Postgres active**

Ensure Docker is up: `docker compose -f docker/docker-compose.yml -p mcp-sqlite-lab up -d`
Run: `PG_DSN="postgresql://lab:lab@localhost:55432/lab" uv run pytest -v`
Expected: every test PASS, including `TestPostgresContract`.

- [ ] **Step 3: Run `verify_server.py` against SQLite**

Run: `uv run python implementation/verify_server.py`
Expected: `Summary: 14 passed, 0 failed`.

- [ ] **Step 4: Run `verify_server.py` against Postgres**

Run: `DB_BACKEND=postgres PG_DSN="postgresql://lab:lab@localhost:55432/lab" uv run python implementation/verify_server.py`
Expected: same 14 PASS.

- [ ] **Step 5: HTTP auth manual check (two curls)**

Terminal 1:
```bash
export MCP_AUTH_TOKEN="dev-secret-token"
uv run python implementation/mcp_server.py --transport http --port 8765
```

Terminal 2:
```bash
curl -i -sS -X POST http://127.0.0.1:8765/mcp \
    -H "Content-Type: application/json" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
# Expected: HTTP/1.1 401

curl -i -sS -X POST http://127.0.0.1:8765/mcp \
    -H "Authorization: Bearer dev-secret-token" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
# Expected: HTTP/1.1 200, body lists the three tools
```

Stop the HTTP server with Ctrl-C.

- [ ] **Step 6: Teardown Postgres**

Run: `bash scripts/teardown.sh`
Expected: containers + volume removed, the message `✓ Removed mcp-sqlite-lab containers, network, and volumes.` Run `docker volume ls | grep mcp-sqlite-lab` — expect no output.

- [ ] **Step 7: Single consolidated commit**

Run:
```bash
git add -A
git status
```

Verify only the intended files are staged (no `.venv`, no `lab.db`, no `.npm-cache`, no `__pycache__`). If any of those slipped in, add a `.gitignore`:

```gitignore
.venv/
__pycache__/
*.pyc
.pytest_cache/
.npm-cache/
lab.db
```

Then `git add .gitignore && git rm -r --cached .venv __pycache__ 2>/dev/null || true && git add -A`.

Commit (no Co-Authored-By, per repo memory):

```bash
git commit -m "$(cat <<'EOF'
Implement Day 26 Track 3 MCP SQLite lab (base + full bonus)

- FastMCP server exposing search, insert, aggregate tools
- schema://database and schema://table/{table_name} resources
- DatabaseAdapter ABC with SQLite and Postgres implementations
- Validation layer rejects unknown identifiers, operators, metrics, empty inserts
- Bearer-token auth for HTTP transport (constant-time compare, fail-closed startup)
- pytest suite (validators, both adapters, tools, resources, auth)
- verify_server.py E2E smoke (14 checks, PASS/FAIL output)
- docker-compose isolated under project name mcp-sqlite-lab with teardown script
- Inspector helper script with absolute paths
- README with setup, client configs, demo shots, teardown
EOF
)"
```

- [ ] **Step 8: Confirm clean state**

Run: `git log --oneline -1 && git status`
Expected: one new commit at HEAD, working tree clean.

---

## Spec Coverage Check

| Spec section | Plan task(s) |
|---|---|
| §1 Goal — full bonus | All tasks |
| §2 Architecture — three layers | Tasks 4, 9, 11 |
| §3 Repo layout | All file paths in Tasks 1–15 |
| §4 Data model | Tasks 5, 12 |
| §5 Database adapter layer | Tasks 3, 4, 5, 6, 7, 8, 12 |
| §6 MCP surface | Tasks 9, 10 |
| §7 Auth | Task 11 |
| §8 Testing & verification | Tasks 3, 5, 6, 7, 8, 9, 10, 11, 12, 13 |
| §9 Docker, configs, demo | Tasks 12, 14, 15 |
| §10 Rubric mapping | Verified by Task 16 steps 1–6 |
| §11 Risks | Notes inside Task 11 (FastMCP API), Task 12 (Postgres) |
