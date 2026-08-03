from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP
from fastmcp.apps import AppConfig
from fastmcp.tools import ToolResult
from mcp.types import TextContent
from pydantic import BaseModel, ConfigDict

from .service import ChecklistService, run_tool
from .ui import CHECKLIST_HTML, UI_URI


class ToolError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    message: str
    details: Any | None = None


class ToolOutput(BaseModel):
    """Shared structured envelope advertised by every MCP tool."""

    model_config = ConfigDict(extra="forbid")

    summary: str
    affected: dict[str, Any]
    next_steps: list[dict[str, Any]]
    conflicts: list[dict[str, Any]] | None = None
    error: ToolError | None = None


def _tool(mcp: FastMCP, *, app: AppConfig | None = None) -> Any:
    return mcp.tool(output_schema=ToolOutput.model_json_schema(), app=app)


def _result(operation: Callable[[], dict[str, Any]]) -> ToolResult:
    payload, is_error = run_tool(operation)
    return ToolResult(
        content=[TextContent(type="text", text=json.dumps(payload, separators=(",", ":")))],
        structured_content=payload,
        is_error=is_error,
    )


def register_tools(mcp: FastMCP, service: ChecklistService) -> None:
    @mcp.resource(UI_URI, mime_type="text/html;profile=mcp-app")
    def journey_checklist_ui() -> str:
        """The rendered journey checklist MCP App."""
        return CHECKLIST_HTML

    app = AppConfig(resource_uri=UI_URI)

    @_tool(mcp)
    def list_blueprints() -> ToolResult:
        """List reusable blueprints with compact item counts."""
        return _result(service.list_blueprints)

    @_tool(mcp)
    def get_blueprint(blueprint_id: str) -> ToolResult:
        """Read one blueprint and its complete current item state."""
        return _result(lambda: service.get_blueprint(blueprint_id))

    @_tool(mcp)
    def create_blueprint(
        name: str,
        items: list[dict[str, Any]] | None = None,
        module_selections: list[dict[str, Any] | str] | None = None,
    ) -> ToolResult:
        """Create a named reusable blueprint from zero or more items."""
        return _result(lambda: service.create_blueprint(name, items, module_selections))

    @_tool(mcp, app=app)
    def start_journey(
        name: str,
        context: dict[str, Any] | None = None,
        blueprint_id: str | None = None,
        module_selections: list[dict[str, Any] | str] | None = None,
    ) -> ToolResult:
        """Start an independent journey, optionally snapshotting a blueprint or modules."""
        return _result(
            lambda: service.start_journey(name, context, blueprint_id, module_selections)
        )

    @_tool(mcp, app=app)
    def get_journey(journey_id: str) -> ToolResult:
        """Read one journey and its complete checklist state."""
        return _result(lambda: service.get_journey(journey_id))

    @_tool(mcp)
    def update_journey(
        journey_id: str,
        name: str | None = None,
        destination: str | None = None,
        purpose: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        duration_days: int | None = None,
        season: str | None = None,
    ) -> ToolResult:
        """Update journey name or context without changing its items."""
        updates = {
            key: value
            for key, value in {
                "name": name,
                "destination": destination,
                "purpose": purpose,
                "start_date": start_date,
                "end_date": end_date,
                "duration_days": duration_days,
                "season": season,
            }.items()
            if value is not None
        }
        return _result(lambda: service.update_journey(journey_id, updates))

    @_tool(mcp)
    def add_items(target_type: str, target_id: str, items: list[dict[str, Any]]) -> ToolResult:
        """Add concrete items to one explicit journey or blueprint target."""
        return _result(lambda: service.add_items(target_type, target_id, items))

    @_tool(mcp)
    def update_items(target_type: str, target_id: str, updates: list[dict[str, Any]]) -> ToolResult:
        """Edit concrete item details or packed/not-needed state by stable item ID."""
        return _result(lambda: service.update_items(target_type, target_id, updates))

    @_tool(mcp)
    def remove_items(target_type: str, target_id: str, item_ids: list[str]) -> ToolResult:
        """Remove selected items from one explicit target."""
        return _result(lambda: service.remove_items(target_type, target_id, item_ids))

    @_tool(mcp)
    def promote_items(
        journey_id: str,
        item_ids: list[str],
        blueprint_id: str | None = None,
        new_blueprint_name: str | None = None,
    ) -> ToolResult:
        """Explicitly copy direct journey items into an existing or new blueprint."""
        return _result(
            lambda: service.promote_items(journey_id, item_ids, blueprint_id, new_blueprint_name)
        )

    @_tool(mcp)
    def list_modules() -> ToolResult:
        """List reusable composable modules with variant, include, and choice metadata."""
        return _result(service.list_modules)

    @_tool(mcp)
    def get_module(module_id: str) -> ToolResult:
        """Read one module, including stable items, variant deltas, includes, and choices."""
        return _result(lambda: service.get_module(module_id))

    @_tool(mcp)
    def create_module(
        name: str,
        common_items: list[dict[str, Any]] | None = None,
        variants: list[dict[str, Any]] | None = None,
        includes: list[dict[str, Any] | str] | None = None,
        choices: list[dict[str, Any]] | None = None,
        description: str | None = None,
    ) -> ToolResult:
        """Create a reusable module from stable items and explicit composition metadata."""
        return _result(
            lambda: service.create_module(
                name, common_items, variants, includes, choices, description
            )
        )

    @_tool(mcp)
    def update_module(
        module_id: str,
        name: str | None = None,
        description: str | None = None,
        common_items: list[dict[str, Any]] | None = None,
        variants: list[dict[str, Any]] | None = None,
        includes: list[dict[str, Any] | str] | None = None,
        choices: list[dict[str, Any]] | None = None,
    ) -> ToolResult:
        """Update module definitions without rewriting existing materialized targets."""
        return _result(
            lambda: service.update_module(
                module_id, name, description, common_items, variants, includes, choices
            )
        )

    @_tool(mcp)
    def delete_module(module_id: str) -> ToolResult:
        """Delete an unused module definition."""
        return _result(lambda: service.delete_module(module_id))

    @_tool(mcp)
    def include_module(
        target_type: str,
        target_id: str,
        module_id: str,
        variant: str | None = None,
        choices: dict[str, str] | list[dict[str, Any]] | None = None,
        selection_id: str | None = None,
    ) -> ToolResult:
        """Select and materialize one module into a journey or blueprint."""
        return _result(
            lambda: service.include_module(
                target_type, target_id, module_id, variant, choices, selection_id
            )
        )

    @_tool(mcp)
    def select_module_option(
        target_type: str,
        target_id: str,
        choice_id: str,
        option_key: str,
        selection_id: str | None = None,
    ) -> ToolResult:
        """Explicitly resolve one module one-of choice and materialize its option."""
        return _result(
            lambda: service.select_module_option(
                target_type, target_id, choice_id, option_key, selection_id
            )
        )

    @_tool(mcp)
    def refresh_composition(target_type: str, target_id: str) -> ToolResult:
        """Explicitly refresh selected modules while preserving edits and removals."""
        return _result(lambda: service.refresh_composition(target_type, target_id))
