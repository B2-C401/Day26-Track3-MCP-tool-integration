import asyncio
import os
import socket

import httpx
import pytest

from implementation.db.sqlite_adapter import SQLiteAdapter
from implementation.mcp_server import build_server
from implementation.auth import make_bearer_middleware


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
async def http_server(seeded_sqlite_path, monkeypatch):
    monkeypatch.setenv("MCP_AUTH_TOKEN", "test-token-123")
    adapter = SQLiteAdapter(str(seeded_sqlite_path))
    mcp = build_server(adapter)
    middleware = make_bearer_middleware()

    port = _free_port()
    task = asyncio.create_task(
        mcp.run_http_async(host="127.0.0.1", port=port, middleware=middleware, stateless_http=True)
    )
    # Wait until the port responds
    for _ in range(80):
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
    except (asyncio.CancelledError, Exception):
        pass
    adapter.close()


@pytest.fixture
def env_no_token(monkeypatch):
    monkeypatch.delenv("MCP_AUTH_TOKEN", raising=False)


class TestAuthStartup:
    def test_missing_env_token_refuses(self, env_no_token):
        with pytest.raises(RuntimeError, match="MCP_AUTH_TOKEN"):
            make_bearer_middleware()


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
