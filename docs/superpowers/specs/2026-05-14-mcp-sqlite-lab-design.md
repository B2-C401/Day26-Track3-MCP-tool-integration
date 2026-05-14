# Design — Day 26 Track 3: FastMCP SQLite Lab (Full Bonus)

- **Date:** 2026-05-14
- **Target score:** 100 base + up to 10 bonus
- **Status:** Approved by user during brainstorming

## 1. Goal and Scope

Implement the lab described in `README.md` end-to-end with all bonus features pursued:

- FastMCP server exposing `search`, `insert`, `aggregate` tools and `schema://database` + `schema://table/{table_name}` resources.
- Stdio transport by default; HTTP transport with Bearer-token auth as a runtime option (bonus).
- Database access through a swappable adapter interface with two implementations: SQLite (primary) and PostgreSQL (bonus, runs via Docker).
- `pytest` suite plus a single `verify_server.py` smoke script that produces PASS/FAIL output.
- Demo via MCP Inspector and Gemini CLI.
- All Docker resources isolated under project name `mcp-sqlite-lab` and removable with a single teardown script.

Out of scope: extra tools beyond the three required (no `delete`/`update`), OAuth, rate limiting, IP allowlists, large-payload pagination tokens, multi-token auth.

## 2. Architecture Overview

```
MCP client (Inspector / Gemini CLI / curl)
        │  stdio  or  HTTP + Bearer
        ▼
mcp_server.py — FastMCP
  - @mcp.tool: search / insert / aggregate
  - @mcp.resource: schema://database, schema://table/{table_name}
  - BearerAuthMiddleware (HTTP transport only)
        │
        ▼
db/  — Database layer
  - base.py            DatabaseAdapter (ABC)
  - sqlite_adapter.py  SQLiteAdapter
  - postgres_adapter.py PostgresAdapter
  - validators.py      identifier / operator / metric checks
  - errors.py          ValidationError, AdapterError
        │
        ▼
SQLite file   |   Postgres (Docker, port 55432)
```

Three layer rule (graded by rubric):
- `mcp_server.py` contains zero SQL. It only wires FastMCP decorators to adapter methods.
- `db/` knows nothing about MCP. It can be unit-tested without FastMCP.
- `db/validators.py` sits between them, validating user-supplied identifiers against the live schema before any SQL is built.

## 3. Repository Layout

```
Day26-Track3-MCP-tool-integration/
├── pyproject.toml              # uv-managed
├── README.md                   # rewritten: setup, demo, teardown
├── .mcp.json                   # sample Claude Code config
├── docker/
│   ├── docker-compose.yml      # project name mcp-sqlite-lab, port 55432
│   └── init.sql                # Postgres schema + seed (parity with SQLite)
├── scripts/
│   ├── teardown.sh             # docker compose down -v --remove-orphans
│   └── run-inspector.sh        # wraps npx with absolute paths
├── implementation/
│   ├── __init__.py
│   ├── mcp_server.py           # FastMCP entrypoint
│   ├── init_db.py              # creates + seeds SQLite
│   ├── verify_server.py        # E2E smoke test, PASS/FAIL
│   ├── auth.py                 # BearerAuthMiddleware
│   ├── db/
│   │   ├── __init__.py
│   │   ├── base.py             # DatabaseAdapter (ABC)
│   │   ├── sqlite_adapter.py
│   │   ├── postgres_adapter.py
│   │   ├── validators.py
│   │   └── errors.py
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_validators.py
│       ├── test_sqlite_adapter.py
│       ├── test_postgres_adapter.py   # skipped unless PG_DSN set
│       ├── test_tools.py
│       ├── test_resources.py
│       └── test_auth.py
└── docs/superpowers/specs/
    └── 2026-05-14-mcp-sqlite-lab-design.md   # this document
```

Pseudocode under `pseudocode/` is left untouched — it is the contract, not runnable code.

## 4. Data Model

Three tables, per the README suggestion. SQLite and Postgres use identical schema; only types differ slightly (`INTEGER PRIMARY KEY AUTOINCREMENT` vs `SERIAL PRIMARY KEY`).

- `students(id, name, cohort, score)` — score for `avg`/`sum`/`min`/`max` demos.
- `courses(id, title, credits)`
- `enrollments(id, student_id, course_id, grade)` — foreign keys to the above.

Seed data: ~10 students across 2 cohorts (`A1`, `B2`), ~4 courses, ~15 enrollments. Small enough to inspect by eye, large enough to make `group_by` interesting.

## 5. Database Adapter Layer

### 5.1 `db/base.py` — interface

```python
class DatabaseAdapter(ABC):
    def list_tables(self) -> list[str]: ...
    def get_table_schema(self, table: str) -> list[dict]: ...
    def get_full_schema(self) -> dict[str, list[dict]]: ...

    def search(
        self, table, columns=None, filters=None,
        order_by=None, descending=False, limit=20, offset=0,
    ) -> dict: ...

    def insert(self, table, values: dict) -> dict: ...

    def aggregate(
        self, table, metric, column=None, filters=None, group_by=None,
    ) -> dict: ...

    def close(self) -> None: ...
```

Return shapes:

- `get_table_schema` → `[{name, type, nullable, primary_key, default}, …]`
- `search` → `{table, columns, rows, count, limit, offset, has_more}`
- `insert` → `{table, inserted, id}`
- `aggregate` → `{table, metric, column, rows: [{group, value}, …]}`

### 5.2 `db/validators.py` — shared validation

```python
ALLOWED_OPERATORS = {"=", "!=", "<", "<=", ">", ">=", "LIKE", "IN"}
ALLOWED_METRICS   = {"count", "avg", "sum", "min", "max"}
IDENTIFIER_RE     = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

validate_identifier(name)        -> str       # syntactic check only
validate_table(adapter, table)   -> str       # must exist in adapter.list_tables()
validate_columns(adapter, t, cs) -> list[str] # all must exist
validate_filters(adapter, t, fs) -> list[dict]
validate_metric(metric)          -> str       # lowercase, in whitelist
validate_insert_values(adapter, t, v) -> dict # non-empty, every key valid
```

Safety rule: identifiers are NEVER parameterized (SQL does not allow it). The adapter only interpolates a table or column name into SQL after that name has been verified to exist in the live schema. All filter and insert *values* always go through driver placeholders (`?` for SQLite, `%s` for psycopg).

### 5.3 SQLite adapter

- `sqlite3.connect(path, check_same_thread=False)`, `row_factory = sqlite3.Row`.
- `list_tables`: `SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'`.
- `get_table_schema`: `PRAGMA table_info("<validated_table>")`, map to dict shape.
- `search`/`insert`/`aggregate`: build SQL with validated identifiers, bind values via `?`.

### 5.4 Postgres adapter

- `psycopg.connect(dsn, autocommit=False)`.
- `list_tables`: `SELECT tablename FROM pg_tables WHERE schemaname='public'`.
- `get_table_schema`: join `information_schema.columns` and primary-key info, return same dict shape.
- Use `%s` placeholders; identifiers quoted with `psycopg.sql.Identifier` for an extra safety belt.

### 5.5 Backend selection

```python
backend = os.getenv("DB_BACKEND", "sqlite")
if backend == "sqlite":
    adapter = SQLiteAdapter(os.getenv("SQLITE_PATH", "lab.db"))
elif backend == "postgres":
    adapter = PostgresAdapter(os.getenv("PG_DSN", "postgresql://lab:lab@localhost:55432/lab"))
else:
    raise SystemExit(f"unknown DB_BACKEND={backend!r}")
```

## 6. MCP Surface

### 6.1 Tools

`search(table, columns?, filters?, order_by?, descending?, limit=20, offset=0)`
- Validates table, columns, filters, `order_by`.
- Clamps `limit` to [1, 200], `offset >= 0` (rubric bonus: pagination guidance).
- Returns `{table, columns, rows, count, limit, offset, has_more}`.

`insert(table, values)`
- Rejects empty `values`.
- Validates every key as a column of `table`.
- Returns `{table, inserted, id}`.

`aggregate(table, metric, column?, filters?, group_by?)`
- `metric ∈ {count, avg, sum, min, max}` (lowercased).
- `count` may omit `column` (`COUNT(*)`); other metrics require `column`.
- Returns `{table, metric, column, rows: [{group, value}, …]}`.

### 6.2 Resources

`schema://database`
- Returns `{"tables": {<name>: [columns…]}}` as JSON text.
- MIME type `application/json`.

`schema://table/{table_name}`
- Resource template.
- Returns `{"table": <name>, "columns": [columns…]}` as JSON text.
- Unknown `table_name` raises a clear error.

### 6.3 Error handling

A `tool_handler` decorator wraps every tool. `ValidationError` becomes `ToolError("validation: …")`; `AdapterError` becomes `ToolError("database: …")`. The verification script asserts on these prefixes.

### 6.4 Supported filter operators

`=  !=  <  <=  >  >=  LIKE  IN`. `IN` accepts a list value; others accept a scalar. Anything else is rejected at validation time.

## 7. Authentication (HTTP transport bonus)

Default transport is stdio with no auth. When `--transport http` is passed:

- Server reads `MCP_AUTH_TOKEN` from env at startup. **If unset, server refuses to start.**
- Every HTTP request must carry `Authorization: Bearer <token>` matching that env value via `hmac.compare_digest` (constant-time).
- Missing/bad tokens return `401` with `WWW-Authenticate: Bearer realm="mcp"` and `{"error":"unauthorized","reason":…}`.

`BearerAuthMiddleware` lives in `auth.py`. The exact FastMCP middleware API will be confirmed against current docs via `context7` during implementation; if FastMCP does not currently expose a first-class middleware hook for HTTP requests, the fallback is to wrap the FastMCP HTTP ASGI app in a Starlette middleware. Behaviour is unchanged either way.

CLI:

```bash
uv run python implementation/mcp_server.py                       # stdio (default)
MCP_AUTH_TOKEN=dev uv run python implementation/mcp_server.py --transport http --port 8765
```

Demo (two curls in README and replayed by `verify_server.py --http`):

```bash
# missing token -> 401
curl -sS -X POST http://127.0.0.1:8765/mcp -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
# with token -> 200
curl -sS -X POST http://127.0.0.1:8765/mcp \
  -H "Authorization: Bearer dev" -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

## 8. Testing and Verification

### 8.1 Layers

| Layer | File | Runner | Purpose |
|---|---|---|---|
| Unit / integration | `implementation/tests/test_*.py` | `uv run pytest` | Adapter, validators, tool & resource handlers, auth |
| E2E smoke | `implementation/verify_server.py` | `uv run python implementation/verify_server.py` | Spawn server like a client, print PASS/FAIL |

### 8.2 Test files

- `test_validators.py` — identifier regex; metric whitelist; operator whitelist; rejects `";"`, `"OR 1=1"`, `"--"`, spaces, leading digits.
- `test_sqlite_adapter.py` — list_tables; get_table_schema; search with `=`, `LIKE`, `IN`, `>`; pagination; insert returns id; aggregate count/avg/sum/min/max; aggregate with `group_by`; rejects unknown table, unknown column, bad operator, bad metric, empty insert.
- `test_postgres_adapter.py` — runs the same matrix via a shared test base class so SQLite and Postgres share assertions; `pytest.skipif` when `PG_DSN` is unset so CI without Docker still passes.
- `test_tools.py` — uses FastMCP in-process `Client`. `list_tools()` returns exactly the three names. One happy path + one error per tool. Insert-then-search round trip.
- `test_resources.py` — `list_resources()`; resource template discovery; parse JSON for `schema://database` and `schema://table/students`; error for `schema://table/missing`.
- `test_auth.py` — starts HTTP server on random port; 401 without token; 401 with bad token; 200 with good token.

### 8.3 `verify_server.py`

Single script that:
- Spawns the server (stdio by default) and acts as a client.
- Runs 14 checks covering server start, tool discovery, resource discovery, happy and error paths for every tool and resource, and (with `--http URL TOKEN`) auth.
- Prints `[PASS] …` / `[FAIL] …` per check, a summary line, and exits non-zero on any failure.

Mapping to rubric §5 (10 pts): tool discovery (4) → checks 2–4; successful calls (3) → checks 5, 7, 9, 10, 12, 13; failing calls with clear errors (3) → checks 6, 8, 11, 14.

### 8.4 Helper: `scripts/run-inspector.sh`

Wraps `npx -y @modelcontextprotocol/inspector` with absolute paths from `pwd` and a local `NPM_CONFIG_CACHE` directory so it does not pollute the global npm cache (per `Tips.md`).

## 9. Docker, Client Configs, Demo

### 9.1 Docker (Postgres bonus, isolated)

`docker/docker-compose.yml`:
- `name: mcp-sqlite-lab` → all containers, networks, volumes get this prefix.
- `postgres:16-alpine`, container name `mcp-sqlite-lab-postgres`.
- Port mapping `55432:5432` to avoid collision with any existing Postgres on `5432`.
- Named volume `mcp-lab-data` (becomes `mcp-sqlite-lab_mcp-lab-data`).
- Healthcheck via `pg_isready`.
- `init.sql` mounted read-only at `/docker-entrypoint-initdb.d/`.

`scripts/teardown.sh` runs `docker compose -p mcp-sqlite-lab down -v --remove-orphans`. README states explicitly: this only removes resources prefixed `mcp-sqlite-lab` and never touches the user's other Docker state.

### 9.2 Client configs

`.mcp.json` (Claude Code sample, checked in):

```json
{
  "mcpServers": {
    "sqlite-lab": {
      "command": "/ABSOLUTE/PATH/TO/uv",
      "args": ["run", "--directory", "/ABSOLUTE/PATH/TO/REPO", "python", "implementation/mcp_server.py"],
      "env": { "DB_BACKEND": "sqlite", "SQLITE_PATH": "lab.db" }
    }
  }
}
```

Gemini CLI (in README):

```bash
gemini mcp add sqlitelab "$(which uv)" run --directory "$PWD" python implementation/mcp_server.py \
  --description "SQLite lab FastMCP server" --timeout 10000
gemini --allowed-mcp-server-names sqlitelab --yolo -p "List tools and search students cohort A1."
```

Alias `sqlitelab` has no underscore, per `Tips.md`.

### 9.3 Demo video shots (~2 minutes)

Listed in README so the user knows what to record:
1. `uv run pytest` green.
2. `uv run python implementation/verify_server.py` all PASS.
3. Inspector showing 3 tools + 2 resources.
4. Gemini CLI headless call returning data.
5. `MCP_AUTH_TOKEN=dev … --transport http` plus the two curl calls (401 then 200).
6. `docker compose up -d` and `DB_BACKEND=postgres … verify_server.py` showing identical PASS lines.
7. `bash scripts/teardown.sh` removing everything.

## 10. Rubric Mapping

| Rubric section | Points | Where it is earned |
|---|---|---|
| 1. Server foundation | 20 | FastMCP starts; clean `implementation/` layout; `init_db.py` reproducible; `db/` vs `mcp_server.py` split |
| 2. Required tools | 30 | `search` (filters, order, pagination), `insert` (returns payload + id), `aggregate` (count/avg/sum/min/max) |
| 3. MCP resources | 15 | `schema://database` and `schema://table/{table_name}` |
| 4. Safety / errors | 15 | `validators.py` whitelists; parameterized values; `tool_handler` decorator |
| 5. Verification | 10 | `verify_server.py` + pytest covering discovery, happy, error paths |
| 6. Client + demo | 10 | `.mcp.json`, Gemini CLI commands, Inspector script, README + video |
| Bonus: auth | 5 | `BearerAuthMiddleware`, `test_auth.py`, curl demos |
| Bonus: Postgres | 3 | `PostgresAdapter`, `docker-compose.yml`, `test_postgres_adapter.py` |
| Bonus: polish | 2 | Pagination clamp + `has_more`; structured test layout |

## 11. Risks and Open Questions

- **FastMCP middleware API shape**: confirmed at implementation time via `context7`. Fallback is Starlette middleware on the FastMCP ASGI app; behaviour unchanged.
- **`psycopg` packaging**: pin `psycopg[binary]` to avoid requiring a system libpq. Optional dependency group in `pyproject.toml` so SQLite-only users do not need it.
- **Demo video**: must be recorded manually; spec lists shots but cannot automate.
- **Gemini CLI alias collisions**: README instructs the user to remove a pre-existing `sqlitelab` alias before `gemini mcp add` if one is present.
