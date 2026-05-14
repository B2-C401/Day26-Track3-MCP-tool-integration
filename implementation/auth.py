"""Bearer-token auth for HTTP transport.

Uses Starlette BaseHTTPMiddleware and is attached via the `middleware` parameter
of FastMCP's run_http_async() / http_app(), which accepts list[starlette.middleware.Middleware].
"""

from __future__ import annotations

import hmac
import os

from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class _BearerAuthMiddleware(BaseHTTPMiddleware):
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


def make_bearer_middleware() -> list[Middleware]:
    """Build the Bearer-auth middleware list for run_http_async().

    Reads MCP_AUTH_TOKEN at call time. Raises RuntimeError if unset — fail-closed.
    Returns a list ready to pass as the `middleware` parameter.
    """
    token = os.environ.get("MCP_AUTH_TOKEN", "").strip()
    if not token:
        raise RuntimeError(
            "MCP_AUTH_TOKEN must be set when HTTP transport is enabled"
        )
    return [Middleware(_BearerAuthMiddleware, expected_token=token)]
