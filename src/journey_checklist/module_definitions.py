from __future__ import annotations

import re
import sqlite3
from typing import TYPE_CHECKING, Any

from .models import ChecklistError


def stable_key(value: str) -> str:
    key = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return key[:96] or "item"


class ModuleDefinitionMixin:
    if TYPE_CHECKING:

        @staticmethod
        def _id(prefix: str) -> str: ...

        @staticmethod
        def _now() -> str: ...

        @classmethod
        def _text(cls, value: Any, field: str, limit: int = 500) -> str | None: ...

        @classmethod
        def _pack_item_values(cls, item: dict[str, Any]) -> dict[str, Any]: ...

        @classmethod
        def _name(cls, value: Any, field: str = "name") -> str: ...

    @classmethod
    def _key(cls, value: Any, field: str = "item_key") -> str:
        key = cls._text(value, field, 100)
        if not key or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", key):
            raise ChecklistError(
                f"{field} must start with a letter or number and contain only letters, "
                "numbers, '.', '_' or '-'."
            )
        return key

    @classmethod
    def _module_item_values(
        cls, item: dict[str, Any], *, key_field: str = "item_key", allow_missing_key: bool = False
    ) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ChecklistError("Each module item must be an object.")
        raw_key = item.get(key_field, item.get("option_key", item.get("key")))
        if raw_key is None and allow_missing_key:
            raw_key = stable_key(str(item.get("name", "item")))
        return {"item_key": cls._key(raw_key), **cls._pack_item_values(item)}

    @staticmethod
    def _module_item_view(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "item_key": row["item_key"],
            "name": row["name"],
            "group": row["group_name"],
            "quantity": row["quantity"],
            "unit": row["unit"],
            "note": row["note"],
        }

    @classmethod
    def _insert_module_item(
        cls,
        connection: sqlite3.Connection,
        module_id: str,
        item_key: str,
        value: dict[str, Any],
        position: int,
    ) -> None:
        connection.execute(
            """INSERT INTO module_items(
                id, module_id, item_key, name, group_name, quantity, unit, note, position
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cls._id("moduleitem"),
                module_id,
                item_key,
                value["name"],
                value.get("group_name"),
                value["quantity"],
                value.get("unit"),
                value.get("note"),
                position,
            ),
        )

    @classmethod
    def _insert_variant_add(
        cls,
        connection: sqlite3.Connection,
        variant_id: str,
        item_key: str,
        value: dict[str, Any],
        position: int,
    ) -> None:
        connection.execute(
            """INSERT INTO module_variant_adds(
                id, variant_id, item_key, name, group_name, quantity, unit, note, position
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                cls._id("variantitem"),
                variant_id,
                item_key,
                value["name"],
                value.get("group_name"),
                value["quantity"],
                value.get("unit"),
                value.get("note"),
                position,
            ),
        )

    @classmethod
    def _normalize_module_items(
        cls, raw_items: Any, *, field: str, allow_missing_key: bool = True
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_items, list) or len(raw_items) > 50:
            raise ChecklistError(f"{field} must contain at most 50 entries.")
        values: list[dict[str, Any]] = []
        used: set[str] = set()
        for raw in raw_items:
            if not isinstance(raw, dict):
                raise ChecklistError(f"Each {field} entry must be an object.")
            explicit = raw.get("item_key", raw.get("option_key", raw.get("key")))
            base = (
                cls._key(explicit)
                if explicit is not None
                else stable_key(str(raw.get("name", "item")))
            )
            key = base
            suffix = 2
            while key in used:
                if explicit is not None:
                    raise ChecklistError(f"Duplicate item_key: {key}.")
                key = f"{base}-{suffix}"
                suffix += 1
            if explicit is None and not allow_missing_key:
                raise ChecklistError(f"Each {field} entry requires item_key.")
            used.add(key)
            values.append(cls._module_item_values({**raw, "item_key": key}))
        return values

    @classmethod
    def _normalize_variants(
        cls,
        raw_variants: Any,
        common_keys: set[str],
        *,
        allow_missing_key: bool = True,
    ) -> list[dict[str, Any]]:
        if raw_variants is None:
            return []
        if not isinstance(raw_variants, list) or len(raw_variants) > 20:
            raise ChecklistError("variants may contain at most 20 entries.")
        result = []
        labels: set[str] = set()
        for raw in raw_variants:
            if not isinstance(raw, dict):
                raise ChecklistError("Each variant must be an object.")
            label = cls._name(raw.get("label"), "variant label")
            if label in labels:
                raise ChecklistError(f"Duplicate variant label: {label}.")
            labels.add(label)
            add = cls._normalize_module_items(
                raw.get("add", raw.get("items", [])),
                field=f"variant {label} add",
                allow_missing_key=allow_missing_key,
            )
            add_keys = {item["item_key"] for item in add}
            if common_keys & add_keys:
                raise ChecklistError("Variant add item keys must not duplicate common item keys.")
            raw_remove = raw.get("remove", [])
            if not isinstance(raw_remove, list) or len(raw_remove) > 50:
                raise ChecklistError(f"variant {label} remove must contain at most 50 entries.")
            remove = []
            for item in raw_remove:
                key = item.get("item_key", item.get("key")) if isinstance(item, dict) else item
                key = cls._key(key, "remove item_key")
                if key not in common_keys:
                    raise ChecklistError(
                        f"Variant {label} can only remove an item owned by its module: {key}."
                    )
                if key not in remove:
                    remove.append(key)
            result.append({"label": label, "add": add, "remove": remove})
        return result

    @classmethod
    def _normalize_choices(cls, raw_choices: Any) -> list[dict[str, Any]]:
        if raw_choices is None:
            return []
        if not isinstance(raw_choices, list) or len(raw_choices) > 20:
            raise ChecklistError("choices may contain at most 20 entries.")
        result = []
        used: set[str] = set()
        for raw in raw_choices:
            if not isinstance(raw, dict):
                raise ChecklistError("Each choice must be an object.")
            choice_key = raw.get("choice_key", raw.get("key", raw.get("id")))
            choice_key = cls._key(choice_key, "choice_key")
            if choice_key in used:
                raise ChecklistError(f"Duplicate choice_key: {choice_key}.")
            used.add(choice_key)
            options = cls._normalize_module_items(
                raw.get("options", []), field=f"choice {choice_key} options"
            )
            if not options:
                raise ChecklistError(f"Choice {choice_key} must have at least one option.")
            result.append(
                {
                    "choice_key": choice_key,
                    "label": cls._name(raw.get("label", choice_key), "choice label"),
                    "required": bool(raw.get("required", True)),
                    "options": [{"option_key": item.pop("item_key"), **item} for item in options],
                }
            )
        return result

    @classmethod
    def _normalize_includes(cls, connection: sqlite3.Connection, raw_includes: Any) -> list[str]:
        if raw_includes is None:
            return []
        if not isinstance(raw_includes, list) or len(raw_includes) > 50:
            raise ChecklistError("includes may contain at most 50 modules.")
        includes = []
        for raw in raw_includes:
            module_id = raw.get("module_id", raw.get("id")) if isinstance(raw, dict) else raw
            if not isinstance(module_id, str) or not module_id:
                raise ChecklistError("Each include requires module_id.")
            if (
                connection.execute("SELECT 1 FROM modules WHERE id = ?", (module_id,)).fetchone()
                is None
            ):
                raise ChecklistError(f"Unknown module id: {module_id}.", code="not_found")
            includes.append(module_id)
        return includes

    @classmethod
    def _module_edges(cls, connection: sqlite3.Connection) -> dict[str, list[str]]:
        edges: dict[str, list[str]] = {}
        for row in connection.execute(
            "SELECT module_id, included_module_id FROM module_includes ORDER BY position, id"
        ).fetchall():
            edges.setdefault(row["module_id"], []).append(row["included_module_id"])
        return edges

    @classmethod
    def _assert_no_module_cycle(
        cls, connection: sqlite3.Connection, module_id: str, includes: list[str]
    ) -> None:
        edges = cls._module_edges(connection)
        edges[module_id] = includes

        def visit(node: str, stack: tuple[str, ...]) -> None:
            if node in stack:
                cycle = " -> ".join((*stack, node))
                raise ChecklistError(
                    f"Module include cycle rejected: {cycle}.",
                    code="conflict",
                    details={"cycle": [*stack, node]},
                )
            for child in edges.get(node, []):
                visit(child, (*stack, node))

        for node in edges:
            visit(node, ())

    @classmethod
    def _module_from_connection(
        cls, connection: sqlite3.Connection, module_id: str
    ) -> dict[str, Any]:
        row = connection.execute("SELECT * FROM modules WHERE id = ?", (module_id,)).fetchone()
        if row is None:
            raise ChecklistError(f"Unknown module id: {module_id}.", code="not_found")
        common = [
            cls._module_item_view(item)
            for item in connection.execute(
                "SELECT * FROM module_items WHERE module_id = ? ORDER BY position, id", (module_id,)
            ).fetchall()
        ]
        variants = []
        for variant in connection.execute(
            "SELECT * FROM module_variants WHERE module_id = ? ORDER BY position, id", (module_id,)
        ).fetchall():
            adds = [
                {
                    **cls._module_item_view(item),
                    "item_key": item["item_key"],
                }
                for item in connection.execute(
                    "SELECT * FROM module_variant_adds WHERE variant_id = ? ORDER BY position, id",
                    (variant["id"],),
                ).fetchall()
            ]
            removes = [
                item["item_key"]
                for item in connection.execute(
                    "SELECT item_key FROM module_variant_removes "
                    "WHERE variant_id = ? ORDER BY position, item_key",
                    (variant["id"],),
                ).fetchall()
            ]
            variants.append(
                {"id": variant["id"], "label": variant["label"], "add": adds, "remove": removes}
            )
        includes = [
            {
                "module_id": item["included_module_id"],
                "name": item["name"],
                "position": item["position"],
            }
            for item in connection.execute(
                """SELECT mi.included_module_id, mi.position, m.name FROM module_includes mi
                   JOIN modules m ON m.id = mi.included_module_id
                   WHERE mi.module_id = ? ORDER BY mi.position, mi.id""",
                (module_id,),
            ).fetchall()
        ]
        choices = []
        for choice in connection.execute(
            "SELECT * FROM module_choices WHERE module_id = ? ORDER BY position, id", (module_id,)
        ).fetchall():
            options = []
            for option in connection.execute(
                "SELECT * FROM module_choice_options WHERE choice_id = ? ORDER BY position, id",
                (choice["id"],),
            ).fetchall():
                item = {
                    "option_key": option["option_key"],
                    "name": option["name"],
                    "group": option["group_name"],
                    "quantity": option["quantity"],
                    "unit": option["unit"],
                    "note": option["note"],
                }
                options.append(item)
            choices.append(
                {
                    "id": choice["id"],
                    "choice_key": choice["choice_key"],
                    "label": choice["label"],
                    "required": bool(choice["required"]),
                    "options": options,
                }
            )
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "items": common,
            "common": common,
            "variants": variants,
            "includes": includes,
            "choices": choices,
        }
