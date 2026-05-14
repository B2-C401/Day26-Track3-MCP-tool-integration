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
  Rubric.md            grading rubric
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
