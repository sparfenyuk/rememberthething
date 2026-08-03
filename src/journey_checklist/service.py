from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .hints import composition_hints, direct_item_hints, journey_hints
from .models import ChecklistError, result_envelope
from .repository import Repository


class ChecklistService:
    def __init__(self, repository: Repository) -> None:
        self.repository = repository

    def list_blueprints(self) -> dict[str, Any]:
        return result_envelope(
            "Blueprints listed.", {"blueprints": self.repository.list_blueprints()}
        )

    def get_blueprint(self, blueprint_id: str) -> dict[str, Any]:
        return result_envelope(
            "Blueprint loaded.", {"blueprint": self.repository.get_blueprint(blueprint_id)}
        )

    def create_blueprint(
        self,
        name: str,
        items: list[dict[str, Any]] | None = None,
        module_selections: list[dict[str, Any] | str] | None = None,
    ) -> dict[str, Any]:
        blueprint = self.repository.create_blueprint(name, items, module_selections)
        return result_envelope(
            "Blueprint created.",
            {"blueprint": blueprint},
            next_steps=composition_hints(
                "blueprint",
                blueprint["id"],
                blueprint["unresolved_choices"],
                selected_modules=blueprint["selected_modules"],
            ),
            conflicts=blueprint["conflicts"],
        )

    def start_journey(
        self,
        name: str,
        context: dict[str, Any] | None = None,
        blueprint_id: str | None = None,
        module_selections: list[dict[str, Any] | str] | None = None,
    ) -> dict[str, Any]:
        journey = self.repository.start_journey(name, context, blueprint_id, module_selections)
        hints = journey_hints(journey, self.repository.list_modules())
        return result_envelope(
            "Journey started.",
            {"journey": journey},
            next_steps=hints,
            conflicts=journey["conflicts"],
        )

    def get_journey(self, journey_id: str) -> dict[str, Any]:
        journey = self.repository.get_journey(journey_id)
        return result_envelope("Journey loaded.", {"journey": journey})

    def update_journey(self, journey_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        journey = self.repository.update_journey(journey_id, updates)
        hints = journey_hints(journey, self.repository.list_modules())
        return result_envelope("Journey updated.", {"journey": journey}, next_steps=hints)

    def add_items(
        self, target_type: str, target_id: str, items: list[dict[str, Any]]
    ) -> dict[str, Any]:
        changed = self.repository.add_items(target_type, target_id, items)
        hints: list[dict[str, Any]] = []
        if target_type == "journey":
            hints = direct_item_hints(
                changed["target"], changed["item_ids"], changed["target"]["items"]
            )
        return result_envelope("Items added.", changed, next_steps=hints)

    def update_items(
        self, target_type: str, target_id: str, updates: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return result_envelope(
            "Items updated.", self.repository.update_items(target_type, target_id, updates)
        )

    def remove_items(self, target_type: str, target_id: str, item_ids: list[str]) -> dict[str, Any]:
        return result_envelope(
            "Items removed.", self.repository.remove_items(target_type, target_id, item_ids)
        )

    def promote_items(
        self,
        journey_id: str,
        item_ids: list[str],
        blueprint_id: str | None = None,
        new_blueprint_name: str | None = None,
    ) -> dict[str, Any]:
        changed = self.repository.promote_items(
            journey_id, item_ids, blueprint_id, new_blueprint_name
        )
        return result_envelope("Items explicitly promoted.", changed)

    def list_packs(self, journey_id: str | None = None) -> dict[str, Any]:
        return result_envelope("Packs listed.", self.repository.list_packs(journey_id))

    def get_pack(self, pack_id: str) -> dict[str, Any]:
        return result_envelope("Pack loaded.", {"pack": self.repository.get_pack(pack_id)})

    def create_pack(
        self,
        name: str,
        common_items: list[dict[str, Any]],
        variants: list[dict[str, Any]] | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        return result_envelope(
            "Pack created.",
            {"pack": self.repository.create_pack(name, common_items, variants, description)},
        )

    def update_pack(
        self,
        pack_id: str,
        name: str | None = None,
        description: str | None = None,
        common_items: list[dict[str, Any]] | None = None,
        variants: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return result_envelope(
            "Pack updated.",
            {
                "pack": self.repository.update_pack(
                    pack_id, name, description, common_items, variants
                )
            },
        )

    def delete_pack(self, pack_id: str) -> dict[str, Any]:
        return result_envelope("Pack deleted.", self.repository.delete_pack(pack_id))

    def include_pack(
        self, target_type: str, target_id: str, pack_id: str, variant: str | None = None
    ) -> dict[str, Any]:
        changed = self.repository.include_pack(target_type, target_id, pack_id, variant)
        hints: list[dict[str, Any]] = []
        return result_envelope(
            "Pack included."
            if not changed["conflicts"]
            else "Pack included with conflicts preserved.",
            changed,
            next_steps=hints,
            conflicts=changed["conflicts"],
        )

    def list_modules(self) -> dict[str, Any]:
        return result_envelope("Modules listed.", {"modules": self.repository.list_modules()})

    def get_module(self, module_id: str) -> dict[str, Any]:
        return result_envelope("Module loaded.", {"module": self.repository.get_module(module_id)})

    def create_module(
        self,
        name: str,
        common_items: list[dict[str, Any]] | None = None,
        variants: list[dict[str, Any]] | None = None,
        includes: list[dict[str, Any] | str] | None = None,
        choices: list[dict[str, Any]] | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        return result_envelope(
            "Module created.",
            {
                "module": self.repository.create_module(
                    name, common_items, variants, includes, choices, description
                )
            },
        )

    def update_module(
        self,
        module_id: str,
        name: str | None = None,
        description: str | None = None,
        common_items: list[dict[str, Any]] | None = None,
        variants: list[dict[str, Any]] | None = None,
        includes: list[dict[str, Any] | str] | None = None,
        choices: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        return result_envelope(
            "Module updated.",
            {
                "module": self.repository.update_module(
                    module_id, name, description, common_items, variants, includes, choices
                )
            },
        )

    def delete_module(self, module_id: str) -> dict[str, Any]:
        return result_envelope("Module deleted.", self.repository.delete_module(module_id))

    def include_module(
        self,
        target_type: str,
        target_id: str,
        module_id: str,
        variant: str | None = None,
        choices: Any = None,
        selection_id: str | None = None,
    ) -> dict[str, Any]:
        changed = self.repository.include_module(
            target_type, target_id, module_id, variant, choices, selection_id
        )
        hints = composition_hints(
            target_type,
            target_id,
            changed["unresolved_choices"],
            selected_modules=changed["target"]["selected_modules"],
            preferred_selection_id=changed["selection_id"],
            conflicts=changed["conflicts"],
        )
        return result_envelope(
            "Module included."
            if not changed["conflicts"]
            else "Module included with conflicts preserved.",
            changed,
            next_steps=hints,
            conflicts=changed["conflicts"],
        )

    def select_module_option(
        self,
        target_type: str,
        target_id: str,
        choice_id: str,
        option_key: str,
        selection_id: str | None = None,
    ) -> dict[str, Any]:
        changed = self.repository.select_module_option(
            target_type, target_id, choice_id, option_key, selection_id
        )
        return result_envelope(
            "Module option selected.",
            changed,
            next_steps=composition_hints(
                target_type,
                target_id,
                changed["unresolved_choices"],
                selected_modules=changed["target"]["selected_modules"],
                preferred_selection_id=changed["selection_id"],
                conflicts=changed["conflicts"],
            ),
            conflicts=changed["conflicts"],
        )

    def refresh_composition(self, target_type: str, target_id: str) -> dict[str, Any]:
        changed = self.repository.refresh_composition(target_type, target_id)
        return result_envelope(
            "Composition refreshed.",
            changed,
            next_steps=composition_hints(
                target_type,
                target_id,
                changed["unresolved_choices"],
                selected_modules=changed["target"]["selected_modules"],
                conflicts=changed["conflicts"],
            ),
            conflicts=changed["conflicts"],
        )


def run_tool(operation: Callable[[], dict[str, Any]]) -> tuple[dict[str, Any], bool]:
    try:
        return operation(), False
    except ChecklistError as exc:
        return {
            "summary": "Operation rejected.",
            "affected": {},
            "next_steps": [],
            "error": exc.as_dict(),
        }, True
    except Exception as exc:  # pragma: no cover - final safety boundary for an MCP process
        return {
            "summary": "Operation failed.",
            "affected": {},
            "next_steps": [],
            "error": {"code": "internal_error", "message": str(exc)},
        }, True
