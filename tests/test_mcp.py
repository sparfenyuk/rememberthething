from __future__ import annotations

import asyncio
import json
import os
from importlib import import_module

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


@pytest.mark.asyncio
async def test_mcp_initialize_tools_and_tool_only_flow(tmp_path, monkeypatch):
    monkeypatch.setenv("JOURNEY_CHECKLIST_DB", str(tmp_path / "mcp.sqlite3"))
    monkeypatch.delenv("LMSTASH_ORIGIN_TOKEN", raising=False)
    from src.server import create_app

    app = create_app(tmp_path / "mcp.sqlite3")
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with streamable_http_client(
                "http://testserver/mcp", http_client=client
            ) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    initialized = await session.initialize()
                    assert initialized.serverInfo.name == "Journey Checklist"
                    tools = await session.list_tools()
                    names = {tool.name for tool in tools.tools}
                    assert {"start_journey", "add_items", "include_pack", "get_journey"} <= names
                    created = await session.call_tool("start_journey", {"name": "Berlin"})
                    payload = json.loads(created.content[0].text)
                    assert payload["affected"]["journey"]["name"] == "Berlin"


def test_ui_contract_is_registered():
    os.environ.setdefault("JOURNEY_CHECKLIST_DB", "/tmp/journey-checklist-test.sqlite3")
    create_app = import_module("src.server").create_app
    UI_URI = import_module("src.journey_checklist.ui").UI_URI

    app = create_app("/tmp/journey-checklist-test.sqlite3")
    resource = asyncio.run(app.state.mcp.get_resource(UI_URI))
    assert resource is not None
