# Báo Cáo Cá Nhân — Day 26 Track 3: MCP Tool Integration

**Họ và tên:** Trương Minh Tiền
**Ngày thực hiện:** 14/05/2026
**Dự án:** Xây dựng MCP Server với FastMCP và SQLite

---

## 1. Tổng Quan

Bài lab yêu cầu xây dựng một MCP (Model Context Protocol) server sử dụng FastMCP, kết nối với cơ sở dữ liệu SQLite, và expose các tool cũng như resource cho AI client sử dụng. Ngoài phần cơ bản, tôi đã hoàn thiện toàn bộ phần bonus bao gồm HTTP transport với xác thực Bearer token và PostgreSQL adapter.

---

## 2. Những Gì Đã Làm

### 2.1 Kiến Trúc Hệ Thống

Hệ thống được tổ chức theo **3 layer tách biệt**:

```
MCP Client (Inspector / Gemini CLI / Claude Code / curl)
        │  stdio  hoặc  HTTP + Bearer Token
        ▼
mcp_server.py — FastMCP 3.2.4
  - 3 MCP tools: search / insert / aggregate
  - 2 MCP resources: schema://database, schema://table/{table_name}
  - BearerAuthMiddleware (chỉ bật khi --transport http)
        │
        ▼
db/ — Database layer (không biết về MCP)
  - base.py: DatabaseAdapter (ABC interface)
  - sqlite_adapter.py: SQLiteAdapter
  - postgres_adapter.py: PostgresAdapter
  - validators.py: kiểm tra identifier/operator/metric
  - errors.py: ValidationError, AdapterError
        │
        ▼
SQLite file  |  PostgreSQL (Docker, cổng 55432)
```

**Nguyên tắc thiết kế:**
- `mcp_server.py` không chứa bất kỳ dòng SQL nào
- `db/` không biết về MCP, có thể test độc lập
- Mọi identifier (tên bảng, cột) đều được kiểm tra với schema thật trước khi ghép vào SQL
- Giá trị của user luôn đi qua placeholder (`?` cho SQLite, `%s` cho psycopg)

---

### 2.2 Mô Hình Dữ Liệu

Sử dụng 3 bảng quan hệ để demo đầy đủ tính năng:

| Bảng | Cột chính | Mục đích |
|---|---|---|
| `students` | id, name, cohort, score | Demo filter, aggregate avg/sum/min/max |
| `courses` | id, title, credits | Demo join tiềm năng |
| `enrollments` | id, student_id, course_id, grade | Bảng liên kết |

Seed data: **10 sinh viên** (4 cohort A1, 6 cohort B2), **4 môn học**, **15 đăng ký**.

---

### 2.3 MCP Tools

#### `search` — Tìm kiếm dữ liệu

```python
search(
    table: str,
    columns?: list[str],        # chọn cột, mặc định tất cả
    filters?: list[dict],       # [{column, op, value}]
    order_by?: str,
    descending?: bool,
    limit?: int = 20,           # clamp [1, 200]
    offset?: int = 0,
)
# Trả về: {table, columns, rows, count, limit, offset, has_more}
```

**Ví dụ:**
```json
{
  "table": "students",
  "filters": [{"column": "cohort", "op": "=", "value": "A1"}],
  "order_by": "score",
  "descending": true,
  "limit": 10
}
```

Operator được hỗ trợ: `=`, `!=`, `<`, `<=`, `>`, `>=`, `LIKE`, `IN`

#### `insert` — Thêm dữ liệu

```python
insert(table: str, values: dict)
# Trả về: {table, inserted, id}
```

#### `aggregate` — Tổng hợp số liệu

```python
aggregate(
    table: str,
    metric: str,        # count | avg | sum | min | max
    column?: str,
    filters?: list[dict],
    group_by?: str,
)
# Trả về: {table, metric, column, rows: [{group, value}]}
```

**Ví dụ:** điểm trung bình theo cohort
```json
{"table": "students", "metric": "avg", "column": "score", "group_by": "cohort"}
```

---

### 2.4 MCP Resources

| URI | Mô tả |
|---|---|
| `schema://database` | Toàn bộ schema DB dạng JSON |
| `schema://table/{table_name}` | Schema của một bảng cụ thể |

---

### 2.5 Validation và Bảo Mật

Đây là phần quan trọng nhất để đảm bảo server an toàn:

```python
# validators.py
ALLOWED_OPERATORS = frozenset({"=", "!=", "<", "<=", ">", ">=", "LIKE", "IN"})
ALLOWED_METRICS   = frozenset({"count", "avg", "sum", "min", "max"})
IDENTIFIER_RE     = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
```

**Quy trình xử lý mỗi request:**
1. Kiểm tra cú pháp identifier (regex) — ngăn ký tự đặc biệt, space, dấu chấm phẩy
2. Kiểm tra tên bảng/cột tồn tại trong schema thật (live schema check)
3. Kiểm tra operator và metric nằm trong whitelist cứng
4. Ghép SQL bằng identifier đã validated + bind value qua placeholder

**Điều này ngăn chặn:**
- SQL injection qua tên bảng/cột
- Operator injection (`OR 1=1`, `--`)
- Metric injection (`DROP TABLE`, `1=1`)
- Insert rỗng

---

### 2.6 HTTP Transport + Bearer Auth (Bonus)

Server mặc định chạy **stdio** (không cần auth). Khi bật `--transport http`:

```bash
export MCP_AUTH_TOKEN="your-secret-token"
uv run python implementation/mcp_server.py --transport http --port 8765
```

Cơ chế xác thực:
- Mỗi request phải có header `Authorization: Bearer <token>`
- So sánh token bằng `hmac.compare_digest()` (constant-time, chống timing attack)
- **Fail-closed**: nếu `MCP_AUTH_TOKEN` không được set, server từ chối khởi động
- Request không có token hoặc token sai → `401 Unauthorized`

```bash
# Không có token → 401
curl -X POST http://127.0.0.1:8765/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'

# Có token hợp lệ → 200
curl -X POST http://127.0.0.1:8765/mcp \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}'
```

---

### 2.7 PostgreSQL Adapter (Bonus)

Thiết kế `DatabaseAdapter` dạng ABC (Abstract Base Class) cho phép thay thế SQLite bằng PostgreSQL mà không thay đổi bất kỳ dòng code nào ở `mcp_server.py`.

```bash
# Khởi động Postgres (cổng 55432, không đụng Postgres khác trên máy)
docker compose -f docker/docker-compose.yml -p mcp-sqlite-lab up -d

# Chạy server với Postgres
DB_BACKEND=postgres \
PG_DSN="postgresql://lab:lab@localhost:55432/lab" \
  uv run python implementation/mcp_server.py

# Dọn dẹp hoàn toàn (chỉ xóa resource có prefix mcp-sqlite-lab)
bash scripts/teardown.sh
```

**Kỹ thuật cô lập Docker:**
- `name: mcp-sqlite-lab` → tất cả container/network/volume được prefix riêng
- Cổng `55432` (không phải `5432`) → không xung đột Postgres đang chạy
- `scripts/teardown.sh` → xóa sạch sau khi demo

---

## 3. Kiểm Thử

### 3.1 Pytest Suite — 85 tests

| File test | Số test | Nội dung |
|---|---|---|
| `test_validators.py` | 41 | Identifier regex, metric whitelist, operator whitelist, schema-aware checks |
| `test_sqlite_adapter.py` | 27 | list_tables, schema, search (11 case), insert (5 case), aggregate (8 case) |
| `test_postgres_adapter.py` | 27 | Cùng bộ test SQLite, skip nếu không có `PG_DSN` |
| `test_tools.py` | 8 | FastMCP Client in-process, tool discovery, happy/error paths |
| `test_resources.py` | 5 | Resource discovery, đọc JSON, error case |
| `test_auth.py` | 4 | Startup refusal, 401 missing, 401 bad token, 200 valid |

```
======================== 85 passed, 27 skipped in 3.88s ========================
```
*(27 skipped = Postgres tests khi không có Docker)*

### 3.2 E2E Smoke Test — 14 checks

```
[PASS] server starts and lists tools
[PASS] tools/list returns search, insert, aggregate
[PASS] resources/list returns schema://database
[PASS] resources/templates/list returns schema://table/{table_name}
[PASS] search valid: returns rows
[PASS] search invalid table: returns error
[PASS] insert valid: returns inserted payload
[PASS] insert empty: returns error
[PASS] aggregate count: returns number
[PASS] aggregate avg by group: returns grouped rows
[PASS] aggregate invalid metric: returns error
[PASS] resource schema://database: JSON parses with tables key
[PASS] resource schema://table/students: parses, has columns
[PASS] resource schema://table/missing: returns error

Summary: 14 passed, 0 failed
```

---

## 4. Cấu Trúc Dự Án

```
Day26-Track3-MCP-tool-integration/
├── pyproject.toml              # uv, deps, pytest config
├── uv.lock                     # lockfile tái tạo chính xác
├── .mcp.json                   # config mẫu cho Claude Code
├── .gitignore
├── README.md                   # Hướng dẫn setup và demo
├── Rubric.md                   # Rubric chấm điểm
├── docker/
│   ├── docker-compose.yml      # Postgres isolated (project: mcp-sqlite-lab)
│   └── init.sql                # Schema + seed data cho Postgres
├── scripts/
│   ├── run-inspector.sh        # Chạy MCP Inspector với absolute paths
│   └── teardown.sh             # Xóa Docker resources
├── implementation/
│   ├── mcp_server.py           # FastMCP entrypoint (tools + resources)
│   ├── init_db.py              # Tạo và seed SQLite DB
│   ├── verify_server.py        # E2E smoke test (14 checks)
│   ├── auth.py                 # Bearer token middleware
│   ├── db/
│   │   ├── base.py             # DatabaseAdapter (ABC)
│   │   ├── sqlite_adapter.py   # SQLiteAdapter
│   │   ├── postgres_adapter.py # PostgresAdapter
│   │   ├── validators.py       # Validation layer
│   │   └── errors.py           # ValidationError, AdapterError
│   └── tests/
│       ├── conftest.py
│       ├── _adapter_contract.py
│       ├── test_validators.py
│       ├── test_sqlite_adapter.py
│       ├── test_postgres_adapter.py
│       ├── test_tools.py
│       ├── test_resources.py
│       └── test_auth.py
└── docs/
    ├── lab-spec.md             # Lab spec gốc
    └── superpowers/
        ├── specs/              # Design document
        └── plans/              # Implementation plan
```

---

## 5. Hướng Dẫn Chạy Nhanh

```bash
# 1. Cài đặt
uv sync --extra dev --extra postgres

# 2. Khởi tạo DB
uv run python implementation/init_db.py

# 3. Chạy tests
uv run pytest -v

# 4. Chạy E2E smoke test
uv run python implementation/verify_server.py

# 5. Chạy server (stdio)
uv run python implementation/mcp_server.py

# 6. Mở Inspector
bash scripts/run-inspector.sh
```

---

## 6. Những Phát Hiện Kỹ Thuật

Trong quá trình thực hiện, tôi gặp và giải quyết một số vấn đề thực tế:

1. **FastMCP 3.x thay đổi API so với 2.x**: Version được resolve là `3.2.4`, không phải `2.x` như spec đề cập. Một số điểm khác biệt:
   - `add_middleware()` là MCP protocol middleware, **không phải** HTTP middleware
   - HTTP middleware phải truyền qua `run_http_async(middleware=[starlette.middleware.Middleware(...)])`
   - HTTP transport mặc định là **stateful** (cần `initialize` handshake); phải dùng `stateless_http=True` cho curl/simple clients

2. **Relative imports trong Python**: Khi chạy `python implementation/mcp_server.py` trực tiếp, Python không nhận `__package__`, gây `ImportError`. Giải pháp: kiểm tra `__package__` lúc khởi động và switch giữa relative và absolute import.

3. **Postgres test isolation**: `insert()` gọi `conn.commit()`, khiến dữ liệu từ test trước ảnh hưởng test sau. Giải pháp: monkeypatch `commit` thành no-op trong fixture, rollback sau mỗi test.

4. **`psycopg.sql.Placeholder()` dùng như list**: Cú pháp `[sql.Placeholder()] * n` đúng hơn `sql.Placeholder() * n` trong psycopg3.

---

## 7. Tự Đánh Giá Rubric

| Mục | Điểm tối đa | Tự đánh giá | Ghi chú |
|---|---|---|---|
| Server foundation | 20 | 20 | FastMCP khởi động, cấu trúc sạch, init_db.py tái tạo được, tách db/ vs server |
| Required tools | 30 | 30 | search/insert/aggregate đầy đủ, filter, pagination, group_by |
| MCP resources | 15 | 15 | schema://database và schema://table/{table_name} |
| Safety & errors | 15 | 15 | Validate identifier, operator whitelist, parameterized values |
| Verification | 10 | 10 | pytest 85 tests + verify_server.py 14 checks |
| Client + demo | 10 | 9 | .mcp.json, Gemini CLI, Inspector; thiếu video demo |
| **Bonus: HTTP auth** | +5 | +5 | Bearer middleware, fail-closed, constant-time compare |
| **Bonus: PostgreSQL** | +3 | +3 | PostgresAdapter, Docker isolated, test suite |
| **Bonus: Polish** | +2 | +2 | Pagination clamp, has_more, structured tests |
| **Tổng** | **110** | **109** | |

---

## 8. Kết Luận

Bài lab đã được hoàn thiện với đầy đủ tính năng cơ bản và toàn bộ phần bonus. Điểm nổi bật:

- **Kiến trúc rõ ràng**: Tách biệt MCP layer và Database layer, code dễ đọc và maintain
- **An toàn thực sự**: Validation chặt chẽ, không concatenate string vào SQL
- **Có thể mở rộng**: DatabaseAdapter ABC cho phép thêm database backend mới mà không sửa server
- **Test coverage cao**: 85 unit/integration tests + 14 E2E checks
- **Bonus hoàn chỉnh**: HTTP auth và PostgreSQL adapter hoạt động thực tế, không chỉ là stub

