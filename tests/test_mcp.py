from __future__ import annotations

import asyncio
import json
import os
from importlib import import_module

import httpx
import pytest
from jsonschema import Draft202012Validator
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


@pytest.mark.asyncio
async def test_create_blueprint_advertises_and_matches_output_schema(tmp_path, monkeypatch):
    monkeypatch.setenv("JOURNEY_CHECKLIST_DB", str(tmp_path / "blueprint-schema.sqlite3"))
    monkeypatch.delenv("LMSTASH_ORIGIN_TOKEN", raising=False)
    from src.server import create_app

    app = create_app(tmp_path / "blueprint-schema.sqlite3")
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            async with streamable_http_client(
                "http://testserver/mcp", http_client=client
            ) as streams:
                async with ClientSession(streams[0], streams[1]) as session:
                    await session.initialize()
                    tool = next(
                        tool
                        for tool in (await session.list_tools()).tools
                        if tool.name == "create_blueprint"
                    )
                    assert tool.outputSchema is not None
                    Draft202012Validator.check_schema(tool.outputSchema)

                    created = await session.call_tool(
                        "create_blueprint",
                        {"name": "carry-on", "items": [{"name": "passport", "group": "documents"}]},
                    )
                    assert created.isError is False
                    assert created.structuredContent is not None
                    Draft202012Validator(tool.outputSchema).validate(created.structuredContent)
                    assert json.loads(created.content[0].text) == created.structuredContent

                    rejected = await session.call_tool("create_blueprint", {"name": "carry-on"})
                    assert rejected.isError is True
                    assert rejected.structuredContent is not None
                    Draft202012Validator(tool.outputSchema).validate(rejected.structuredContent)


@pytest.mark.asyncio
async def test_origin_token_auth_statuses_and_healthz(tmp_path, monkeypatch):
    monkeypatch.setenv("LMSTASH_ORIGIN_TOKEN", "secret")
    monkeypatch.delenv("MCP_ORIGIN_TOKEN", raising=False)
    from src.server import create_app

    app = create_app(tmp_path / "auth.sqlite3")
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            for headers, expected_status in (
                ({}, 401),
                ({"X-LMStash-Origin-Token": "wrong"}, 401),
                ({"X-LMStash-Origin-Token": "secret"}, 405),
            ):
                response = await client.get("/mcp", headers=headers)
                assert response.status_code == expected_status

            response = await client.get("/healthz")
            assert response.status_code == 200


def test_ui_contract_is_registered():
    os.environ.setdefault("JOURNEY_CHECKLIST_DB", "/tmp/journey-checklist-test.sqlite3")
    create_app = import_module("src.server").create_app
    UI_URI = import_module("src.journey_checklist.ui").UI_URI

    app = create_app("/tmp/journey-checklist-test.sqlite3")
    resource = asyncio.run(app.state.mcp.get_resource(UI_URI))
    assert resource is not None


def test_ui_contract_uses_mcp_app_lifecycle_and_tool_notifications():
    ui = import_module("src.journey_checklist.ui")
    assert "sendRequest('ui/initialize'" in ui.CHECKLIST_HTML
    assert "ui/notifications/initialized" in ui.CHECKLIST_HTML
    assert "ui/notifications/tool-result" in ui.CHECKLIST_HTML
    assert "message?.params" in ui.CHECKLIST_HTML
    assert "value.method === 'tools/call'" not in ui.CHECKLIST_HTML
