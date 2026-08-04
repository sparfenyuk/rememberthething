from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP
from fastmcp.apps import AppConfig
from fastmcp.tools import ToolResult
from mcp.types import TextContent
from pydantic import AliasChoices, BaseModel, ConfigDict, Field

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


class _InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True, strict=True)


class BlueprintItemInput(_InputModel):
    name: str
    group: str | None = Field(default=None, validation_alias=AliasChoices("group", "group_name"))
    quantity: int = 1
    unit: str | None = None
    note: str | None = None
    packed: bool = False
    not_needed: bool = False


class ModuleItemInput(_InputModel):
    item_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("item_key", "option_key", "key"),
    )
    name: str
    group: str | None = Field(default=None, validation_alias=AliasChoices("group", "group_name"))
    quantity: int = 1
    unit: str | None = None
    note: str | None = None


class StableModuleItemInput(ModuleItemInput):
    item_key: str = Field(validation_alias=AliasChoices("item_key", "option_key", "key"))


class OptionInput(_InputModel):
    option_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("option_key", "item_key", "key"),
    )
    name: str
    group: str | None = Field(default=None, validation_alias=AliasChoices("group", "group_name"))
    quantity: int = 1
    unit: str | None = None
    note: str | None = None


class UpdateOptionInput(OptionInput):
    option_key: str = Field(validation_alias=AliasChoices("option_key", "item_key", "key"))


class VariantRemoveInput(_InputModel):
    item_key: str = Field(validation_alias=AliasChoices("item_key", "key"))


class ModuleVariantInput(_InputModel):
    label: str
    add: list[ModuleItemInput] = Field(
        default_factory=list,
        validation_alias=AliasChoices("add", "items"),
    )
    remove: list[str | VariantRemoveInput] = Field(default_factory=list)


class StableModuleVariantInput(_InputModel):
    label: str
    add: list[StableModuleItemInput] = Field(
        default_factory=list,
        validation_alias=AliasChoices("add", "items"),
    )
    remove: list[str | VariantRemoveInput] = Field(default_factory=list)


class ModuleChoiceInput(_InputModel):
    choice_key: str = Field(validation_alias=AliasChoices("choice_key", "key", "id"))
    label: str | None = None
    required: bool = True
    options: list[OptionInput] = Field(min_length=1, max_length=50)


class UpdateModuleChoiceInput(ModuleChoiceInput):
    options: list[UpdateOptionInput] = Field(min_length=1, max_length=50)


class ModuleIncludeInput(_InputModel):
    module_id: str = Field(validation_alias=AliasChoices("module_id", "id"))


class ChoiceSelectionInput(_InputModel):
    module_id: str | None = None
    choice_key: str = Field(validation_alias=AliasChoices("choice_key", "choice_id"))
    option_key: str


ChoiceSelections = dict[str, str] | list[ChoiceSelectionInput]


class ModuleSelectionInput(_InputModel):
    module_id: str = Field(validation_alias=AliasChoices("module_id", "id"))
    variant: str | None = None
    choices: ChoiceSelections | None = Field(
        default=None,
        validation_alias=AliasChoices("choices", "choice_selections"),
    )


class JourneyContextInput(_InputModel):
    destination: str | None = None
    purpose: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    duration_days: int | None = None
    season: str | None = None


def _dump_models(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(exclude_none=True)
    if isinstance(value, list):
        return [_dump_models(item) for item in value]
    if isinstance(value, dict):
        return {key: _dump_models(item) for key, item in value.items()}
    return value


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
        items: list[BlueprintItemInput] | None = None,
        module_selections: list[ModuleSelectionInput | str] | None = None,
    ) -> ToolResult:
        """Create a named reusable blueprint from zero or more items."""
        return _result(
            lambda: service.create_blueprint(
                name, _dump_models(items), _dump_models(module_selections)
            )
        )

    @_tool(mcp, app=app)
    def start_journey(
        name: str,
        context: JourneyContextInput | None = None,
        blueprint_id: str | None = None,
        module_selections: list[ModuleSelectionInput | str] | None = None,
    ) -> ToolResult:
        """Start an independent journey, optionally snapshotting a blueprint or modules."""
        return _result(
            lambda: service.start_journey(
                name,
                _dump_models(context),
                blueprint_id,
                _dump_models(module_selections),
            )
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
        common_items: list[ModuleItemInput] | None = None,
        variants: list[ModuleVariantInput] | None = None,
        includes: list[ModuleIncludeInput | str] | None = None,
        choices: list[ModuleChoiceInput] | None = None,
        description: str | None = None,
    ) -> ToolResult:
        """Create a reusable module from stable items and explicit composition metadata."""
        return _result(
            lambda: service.create_module(
                name,
                _dump_models(common_items),
                _dump_models(variants),
                _dump_models(includes),
                _dump_models(choices),
                description,
            )
        )

    @_tool(mcp)
    def update_module(
        module_id: str,
        name: str | None = None,
        description: str | None = None,
        common_items: list[StableModuleItemInput] | None = None,
        variants: list[StableModuleVariantInput] | None = None,
        includes: list[ModuleIncludeInput | str] | None = None,
        choices: list[UpdateModuleChoiceInput] | None = None,
    ) -> ToolResult:
        """Update module definitions without rewriting existing materialized targets."""
        return _result(
            lambda: service.update_module(
                module_id,
                name,
                description,
                _dump_models(common_items),
                _dump_models(variants),
                _dump_models(includes),
                _dump_models(choices),
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
        choices: ChoiceSelections | None = None,
        selection_id: str | None = None,
    ) -> ToolResult:
        """Select and materialize one module into a journey or blueprint."""
        return _result(
            lambda: service.include_module(
                target_type,
                target_id,
                module_id,
                variant,
                _dump_models(choices),
                selection_id,
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
