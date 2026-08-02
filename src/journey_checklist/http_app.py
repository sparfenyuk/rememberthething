from __future__ import annotations

import json
import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Mount, Route

from .repository import Repository
from .service import ChecklistService
from .tools import register_tools


def storage_path() -> Path:
    return Path(os.getenv("JOURNEY_CHECKLIST_DB", "/data/journey_checklist.sqlite3"))


def _values(name: str, default: list[str]) -> list[str]:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        if raw.lstrip().startswith("["):
            raise RuntimeError(f"{name} must be valid JSON.") from None
        parsed = [part.strip() for part in raw.split(",") if part.strip()]
    if not isinstance(parsed, list) or not all(isinstance(item, str) and item for item in parsed):
        raise RuntimeError(f"{name} must be a JSON array of non-empty strings.")
    return parsed


class OriginTokenMiddleware:
    """Protect MCP traffic at the app boundary when LMStash supplies a token."""

    def __init__(self, app: Any, hosts: list[str], origins: list[str]) -> None:
        self.app = app
        self.hosts = {host.split(":", 1)[0] for host in hosts}
        self.origins = set(origins)
        self.token = os.getenv("LMSTASH_ORIGIN_TOKEN") or os.getenv("MCP_ORIGIN_TOKEN")

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http" or not str(scope.get("path", "")).startswith("/mcp"):
            await self.app(scope, receive, send)
            return
        headers = {key.decode().lower(): value.decode() for key, value in scope.get("headers", [])}
        host = headers.get("host", "").split(":", 1)[0]
        origin = headers.get("origin")
        token = headers.get("x-lmstash-origin-token") or headers.get("x-mcp-origin-token")
        if host not in self.hosts or (origin and origin not in self.origins):
            await self._reject(send, "MCP host or origin is not allowed.")
            return
        if self.token and (not token or not secrets.compare_digest(token, self.token)):
            await self._reject(send, "MCP origin token is missing or invalid.")
            return
        await self.app(scope, receive, send)

    @staticmethod
    async def _reject(send: Any, message: str) -> None:
        body = json.dumps({"error": message}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 403,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


async def healthz(request: Request) -> Response:
    repository: Repository = request.app.state.repository
    ready, detail = repository.ready()
    return JSONResponse(
        {"status": "ok" if ready else "not_ready", "detail": detail},
        status_code=200 if ready else 503,
    )


def create_app(db_path: str | Path | None = None) -> Starlette:
    repository = Repository(db_path or storage_path())
    service = ChecklistService(repository)
    mcp = FastMCP(
        "Journey Checklist",
        version="0.1.0",
        instructions="Use the tools for explicit checklist operations; the LM owns conversational planning and photo understanding.",
        strict_input_validation=True,
    )
    register_tools(mcp, service)
    hosts = _values("LMSTASH_ALLOWED_HOSTS", ["localhost", "127.0.0.1", "testserver"])
    origins = _values(
        "LMSTASH_ALLOWED_ORIGINS", ["http://localhost", "http://127.0.0.1", "http://testserver"]
    )
    mcp_app = mcp.http_app(
        path="/mcp",
        transport="streamable-http",
        stateless_http=True,
        json_response=True,
        allowed_hosts=hosts,
        allowed_origins=origins,
    )

    @asynccontextmanager
    async def lifespan(_: Starlette) -> AsyncIterator[None]:
        repository.initialize()
        async with mcp_app.lifespan(mcp_app):
            yield

    app = Starlette(
        routes=[Route("/healthz", healthz), Mount("/", app=mcp_app)],
        middleware=[Middleware(OriginTokenMiddleware, hosts=hosts, origins=origins)],
        lifespan=lifespan,
    )
    app.state.repository = repository
    app.state.mcp = mcp
    return app
