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

    def _ident(self, name: str) -> sql.Identifier:
        return sql.Identifier(name)

    def _build_where(self, fs: list[dict]) -> tuple:
        if not fs:
            return sql.SQL(""), []
        parts = []
        params: list = []
        for f in fs:
            col, op, val = f["column"], f["op"], f["value"]
            if op == "IN":
                placeholders = sql.SQL(", ").join([sql.Placeholder()] * len(val))
                parts.append(sql.SQL("{c} IN ({ph})").format(c=self._ident(col), ph=placeholders))
                params.extend(val)
            else:
                parts.append(sql.SQL("{c} " + op + " %s").format(c=self._ident(col)))
                params.append(val)
        return sql.SQL(" WHERE ") + sql.SQL(" AND ").join(parts), params

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

        select_cols = sql.SQL(", ").join(self._ident(c) for c in cols)
        stmt = sql.SQL("SELECT {cs} FROM {t}").format(cs=select_cols, t=self._ident(table))
        where, params = self._build_where(fs)
        stmt = stmt + where
        if order_by is not None:
            direction = sql.SQL("DESC") if descending else sql.SQL("ASC")
            stmt = stmt + sql.SQL(" ORDER BY {o} ").format(o=self._ident(order_by)) + direction
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
        stmt = sql.SQL("INSERT INTO {t} ({cs}) VALUES ({ph}) RETURNING id").format(
            t=self._ident(table),
            cs=sql.SQL(", ").join(self._ident(c) for c in cols),
            ph=sql.SQL(", ").join([sql.Placeholder()] * len(cols)),
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
