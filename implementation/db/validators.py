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
