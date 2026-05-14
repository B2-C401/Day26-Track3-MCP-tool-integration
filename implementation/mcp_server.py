"""FastMCP entrypoint. SQL stays out of this module by design."""

from __future__ import annotations

import argparse
import functools
import os
import sys
from pathlib import Path
from typing import Any

# Support both `python -m implementation.mcp_server` and `python implementation/mcp_server.py`
if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from implementation.db.base import DatabaseAdapter
    from implementation.db.errors import AdapterError, ValidationError
    from implementation.db.sqlite_adapter import SQLiteAdapter
else:
    from .db.base import DatabaseAdapter
    from .db.errors import AdapterError, ValidationError
    from .db.sqlite_adapter import SQLiteAdapter

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError


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

    return mcp


def _make_adapter() -> DatabaseAdapter:
    backend = os.getenv("DB_BACKEND", "sqlite").lower()
    if backend == "sqlite":
        return SQLiteAdapter(os.getenv("SQLITE_PATH", "lab.db"))
    if backend == "postgres":
        if __package__ is None or __package__ == "":
            from implementation.db.postgres_adapter import PostgresAdapter
        else:
            from .db.postgres_adapter import PostgresAdapter
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
        if __package__ is None or __package__ == "":
            from implementation.auth import make_bearer_middleware
        else:
            from .auth import make_bearer_middleware
        import asyncio
        middleware = make_bearer_middleware()
        asyncio.run(mcp.run_http_async(host=args.host, port=args.port, middleware=middleware, stateless_http=True))
    else:
        mcp.run()


if __name__ == "__main__":
    main()
