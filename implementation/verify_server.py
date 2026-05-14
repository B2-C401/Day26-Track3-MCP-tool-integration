#!/usr/bin/env python
"""End-to-end smoke test. Prints PASS/FAIL per check; exits 0 iff all pass."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Ensure project root is on sys.path when run as a script (uv run python implementation/verify_server.py)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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


async def run_checks(seed_path: Path) -> Reporter:
    r = Reporter()
    adapter = SQLiteAdapter(str(seed_path))
    server = build_server(adapter)
    try:
        async with Client(server) as c:
            # 1. Server starts
            r.check("server starts and lists tools", True)

            # 2. Tool discovery
            tools = await c.list_tools()
            names = {t.name for t in tools}
            r.check(
                "tools/list returns search, insert, aggregate",
                {"search", "insert", "aggregate"} <= names,
                f"got {sorted(names)}",
            )

            # 3. Resource discovery
            resources = await c.list_resources()
            r.check(
                "resources/list returns schema://database",
                any(str(x.uri) == "schema://database" for x in resources),
            )

            # 4. Resource template discovery
            templates = await c.list_resource_templates()
            r.check(
                "resources/templates/list returns schema://table/{table_name}",
                any(str(t.uriTemplate) == "schema://table/{table_name}" for t in templates),
            )

            # 5. search valid
            res = await c.call_tool(
                "search",
                {"table": "students", "filters": [{"column": "cohort", "op": "=", "value": "A1"}]},
            )
            r.check("search valid: returns rows", len(res.data["rows"]) > 0)

            # 6. search invalid table
            try:
                await c.call_tool("search", {"table": "ghosts"})
                r.check("search invalid table: returns error", False, "no error raised")
            except Exception as e:
                r.check("search invalid table: returns error", "validation" in str(e).lower())

            # 7. insert valid
            res = await c.call_tool(
                "insert",
                {"table": "students", "values": {"name": "Verify", "cohort": "Z9", "score": 7.0}},
            )
            r.check("insert valid: returns inserted payload", res.data.get("id", 0) > 0)

            # 8. insert empty
            try:
                await c.call_tool("insert", {"table": "students", "values": {}})
                r.check("insert empty: returns error", False, "no error raised")
            except Exception as e:
                r.check("insert empty: returns error", "validation" in str(e).lower())

            # 9. aggregate count
            res = await c.call_tool("aggregate", {"table": "students", "metric": "count"})
            r.check("aggregate count: returns number", res.data["rows"][0]["value"] >= 10)

            # 10. aggregate avg by group
            res = await c.call_tool(
                "aggregate",
                {"table": "students", "metric": "avg", "column": "score", "group_by": "cohort"},
            )
            r.check(
                "aggregate avg by group: returns grouped rows",
                len(res.data["rows"]) >= 2,
            )

            # 11. aggregate invalid metric
            try:
                await c.call_tool(
                    "aggregate",
                    {"table": "students", "metric": "median", "column": "score"},
                )
                r.check("aggregate invalid metric: returns error", False)
            except Exception as e:
                r.check("aggregate invalid metric: returns error", "validation" in str(e).lower())

            # 12. resource: schema://database
            res = await c.read_resource("schema://database")
            text = res[0].text
            parsed = json.loads(text)
            r.check("resource schema://database: JSON parses with tables key", "tables" in parsed)

            # 13. resource: schema://table/students
            res = await c.read_resource("schema://table/students")
            text = res[0].text
            parsed = json.loads(text)
            r.check(
                "resource schema://table/students: parses, has columns",
                parsed.get("table") == "students" and len(parsed.get("columns", [])) > 0,
            )

            # 14. resource: schema://table/missing
            try:
                await c.read_resource("schema://table/ghosts")
                r.check("resource schema://table/missing: returns error", False)
            except Exception:
                r.check("resource schema://table/missing: returns error", True)

    finally:
        adapter.close()
    return r


def main():
    parser = argparse.ArgumentParser(description="E2E smoke test for the MCP SQLite server.")
    parser.add_argument("--db", default="lab.db", help="SQLite path (re-seeded each run)")
    args = parser.parse_args()

    db_path = Path(args.db)
    if db_path.exists():
        db_path.unlink()
    init_db.create_schema(db_path)
    init_db.seed(db_path)

    reporter = asyncio.run(run_checks(db_path))
    print(f"\nSummary: {reporter.passed} passed, {reporter.failed} failed")
    sys.exit(0 if reporter.failed == 0 else 1)


if __name__ == "__main__":
    main()
