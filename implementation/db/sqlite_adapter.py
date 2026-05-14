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
            sql = f'SELECT {select} FROM "{table}"'

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
