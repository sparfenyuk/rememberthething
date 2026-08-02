from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any

from .models import ChecklistError, ItemSource


class MaterializationMixin:
    if TYPE_CHECKING:

        @staticmethod
        def _now() -> str: ...

        def _connect(self) -> sqlite3.Connection: ...

        @staticmethod
        def _require_target(
            connection: sqlite3.Connection, target_type: str, target_id: str
        ) -> None: ...

        @classmethod
        def _target(
            cls, connection: sqlite3.Connection, target_type: str, target_id: str
        ) -> dict[str, Any]: ...

        @classmethod
        def _module_from_connection(
            cls, connection: sqlite3.Connection, module_id: str
        ) -> dict[str, Any]: ...

        @classmethod
        def _add_module_selections(
            cls,
            connection: sqlite3.Connection,
            target_type: str,
            target_id: str,
            selections: list[dict[str, Any] | str],
        ) -> list[str]: ...

        @classmethod
        def _validate_choice_option(
            cls,
            connection: sqlite3.Connection,
            module_id: str,
            choice_key: str,
            option_key: str,
            choice_module_id: str | None = None,
        ) -> tuple[str, str, str]: ...

        @classmethod
        def _included_module_ids(
            cls, connection: sqlite3.Connection, module_id: str
        ) -> set[str]: ...

        @classmethod
        def _choice_record(
            cls,
            connection: sqlite3.Connection,
            module_id: str,
            choice_key: str,
            choice_module_id: str | None = None,
        ) -> sqlite3.Row: ...

        def _insert_item(
            self,
            connection: sqlite3.Connection,
            target_type: str,
            target_id: str,
            value: dict[str, Any],
            position: int,
            source: ItemSource,
            composition_key: str | None = None,
        ) -> str: ...

    @classmethod
    def _resolve_module(
        cls,
        connection: sqlite3.Connection,
        module_id: str,
        variant: str | None,
        choice_map: dict[tuple[str, str], str],
        selection_id: str,
        stack: tuple[str, ...],
        path: tuple[str, ...],
        resolved: list[dict[str, Any]],
        unresolved: list[dict[str, Any]],
    ) -> None:
        if module_id in stack:
            raise ChecklistError(
                "Module include cycle encountered while resolving.", code="conflict"
            )
        module = connection.execute("SELECT * FROM modules WHERE id = ?", (module_id,)).fetchone()
        if module is None:
            raise ChecklistError(f"Unknown module id: {module_id}.", code="not_found")
        current_path = (*path, module["name"])
        remove: set[str] = set()
        adds: list[sqlite3.Row] = []
        if variant is not None:
            variant_row = connection.execute(
                "SELECT * FROM module_variants WHERE module_id = ? AND label = ?",
                (module_id, variant),
            ).fetchone()
            if variant_row is None:
                raise ChecklistError(f"Unknown variant {variant!r} for module {module_id}.")
            remove = {
                item[0]
                for item in connection.execute(
                    "SELECT item_key FROM module_variant_removes WHERE variant_id = ?",
                    (variant_row["id"],),
                ).fetchall()
            }
            adds = connection.execute(
                "SELECT * FROM module_variant_adds WHERE variant_id = ? ORDER BY position, id",
                (variant_row["id"],),
            ).fetchall()
        for item in connection.execute(
            "SELECT * FROM module_items WHERE module_id = ? ORDER BY position, id", (module_id,)
        ).fetchall():
            if item["item_key"] in remove:
                continue
            resolved.append(
                cls._resolved_item(
                    item, module_id, module["name"], variant, current_path, selection_id
                )
            )
        for item in adds:
            resolved.append(
                cls._resolved_item(
                    item, module_id, module["name"], variant, current_path, selection_id
                )
            )
        for choice in connection.execute(
            "SELECT * FROM module_choices WHERE module_id = ? ORDER BY position, id", (module_id,)
        ).fetchall():
            option_key = choice_map.get((module_id, choice["choice_key"]))
            options = connection.execute(
                "SELECT * FROM module_choice_options WHERE choice_id = ? ORDER BY position, id",
                (choice["id"],),
            ).fetchall()
            if option_key is None:
                unresolved.append(
                    {
                        "selection_id": selection_id,
                        "module_id": module_id,
                        "module_name": module["name"],
                        "choice_id": choice["id"],
                        "choice_key": choice["choice_key"],
                        "label": choice["label"],
                        "required": bool(choice["required"]),
                        "options": [
                            {"option_key": option["option_key"], "name": option["name"]}
                            for option in options
                        ],
                    }
                )
            else:
                option = next((item for item in options if item["option_key"] == option_key), None)
                if option is None:
                    raise ChecklistError(
                        f"Stored option {option_key!r} is no longer available for "
                        f"choice {choice['choice_key']!r}.",
                        code="conflict",
                    )
                resolved.append(
                    cls._resolved_item(
                        option,
                        module_id,
                        module["name"],
                        variant,
                        current_path,
                        selection_id,
                        choice_key=choice["choice_key"],
                    )
                )
        for include in connection.execute(
            "SELECT included_module_id FROM module_includes "
            "WHERE module_id = ? ORDER BY position, id",
            (module_id,),
        ).fetchall():
            cls._resolve_module(
                connection,
                include["included_module_id"],
                None,
                choice_map,
                selection_id,
                (*stack, module_id),
                current_path,
                resolved,
                unresolved,
            )

    @staticmethod
    def _resolved_item(
        row: sqlite3.Row,
        module_id: str,
        module_name: str,
        variant: str | None,
        path: tuple[str, ...],
        selection_id: str,
        choice_key: str | None = None,
    ) -> dict[str, Any]:
        item_key = row["item_key"] if "item_key" in row.keys() else row["option_key"]
        composition_key = (
            f"module:{module_id}:choice:{choice_key}:{item_key}"
            if choice_key
            else f"module:{module_id}:{item_key}"
        )
        return {
            "name": row["name"],
            "group_name": row["group_name"],
            "quantity": row["quantity"],
            "unit": row["unit"],
            "note": row["note"],
            "composition_key": composition_key,
            "selection_id": selection_id,
            "source": ItemSource("module", module_id, module_name, variant, path),
        }

    @classmethod
    def _resolve_target(
        cls, connection: sqlite3.Connection, target_type: str, target_id: str
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        selections = connection.execute(
            "SELECT * FROM composition_selections "
            "WHERE target_type = ? AND target_id = ? ORDER BY position, id",
            (target_type, target_id),
        ).fetchall()
        resolved: list[dict[str, Any]] = []
        unresolved: list[dict[str, Any]] = []
        for selection in selections:
            choice_map = {
                (choice["module_id"], choice["choice_key"]): choice["option_key"]
                for choice in connection.execute(
                    "SELECT module_id, choice_key, option_key FROM composition_choices "
                    "WHERE selection_id = ?",
                    (selection["id"],),
                ).fetchall()
            }
            cls._resolve_module(
                connection,
                selection["module_id"],
                selection["variant"],
                choice_map,
                selection["id"],
                (),
                (),
                resolved,
                unresolved,
            )
        return resolved, unresolved

    def _materialize(
        self, connection: sqlite3.Connection, target_type: str, target_id: str
    ) -> dict[str, Any]:
        self._require_target(connection, target_type, target_id)
        resolved, unresolved = self._resolve_target(connection, target_type, target_id)
        existing_rows = connection.execute(
            "SELECT * FROM items WHERE target_type = ? AND target_id = ? "
            "ORDER BY position, created_at",
            (target_type, target_id),
        ).fetchall()
        by_composition = {
            row["composition_key"]: row for row in existing_rows if row["composition_key"]
        }
        names = {row["name"].casefold(): row for row in existing_rows}
        exclusions = {
            row["composition_key"]
            for row in connection.execute(
                "SELECT composition_key FROM composition_exclusions "
                "WHERE target_type = ? AND target_id = ?",
                (target_type, target_id),
            ).fetchall()
        }
        conflicts: list[dict[str, Any]] = []
        added_ids: list[str] = []
        position = connection.execute(
            "SELECT COALESCE(MAX(position) + 1, 0) FROM items "
            "WHERE target_type = ? AND target_id = ?",
            (target_type, target_id),
        ).fetchone()[0]
        seen: set[str] = set()
        for candidate in resolved:
            key = candidate["composition_key"]
            if key in exclusions:
                continue
            if key in seen:
                conflicts.append(
                    {
                        "composition_key": key,
                        "reason": "duplicate_source_key",
                        "source": candidate["source"].as_dict(),
                    }
                )
                continue
            seen.add(key)
            existing = by_composition.get(key)
            if existing is not None:
                duplicate = names.get(candidate["name"].casefold())
                if duplicate is not None and duplicate["id"] != existing["id"]:
                    conflicts.append(
                        {
                            "composition_key": key,
                            "name": candidate["name"],
                            "existing_item_id": duplicate["id"],
                            "reason": "duplicate_name_preserved",
                            "edited": bool(duplicate["edited"]),
                        }
                    )
                    continue
                changed = any(
                    existing[field] != candidate.get(field)
                    for field in ("name", "group_name", "quantity", "unit", "note")
                )
                if changed and existing["edited"]:
                    conflicts.append(
                        {
                            "composition_key": key,
                            "existing_item_id": existing["id"],
                            "reason": "edited_target_preserved",
                            "edited": True,
                        }
                    )
                elif changed:
                    connection.execute(
                        "UPDATE items SET name = ?, group_name = ?, quantity = ?, unit = ?, "
                        "note = ?, source_type = ?, source_id = ?, source_label = ?, "
                        "source_variant = ?, source_path = ?, updated_at = ? WHERE id = ?",
                        (
                            candidate["name"],
                            candidate["group_name"],
                            candidate["quantity"],
                            candidate["unit"],
                            candidate["note"],
                            candidate["source"].kind,
                            candidate["source"].source_id,
                            candidate["source"].label,
                            candidate["source"].variant,
                            json.dumps(list(candidate["source"].path)),
                            self._now(),
                            existing["id"],
                        ),
                    )
                continue
            duplicate = names.get(candidate["name"].casefold())
            if duplicate is not None:
                conflicts.append(
                    {
                        "composition_key": key,
                        "name": candidate["name"],
                        "existing_item_id": duplicate["id"],
                        "reason": "duplicate_name_preserved",
                        "edited": bool(duplicate["edited"]),
                    }
                )
                continue
            item_id = self._insert_item(
                connection,
                target_type,
                target_id,
                candidate,
                position,
                candidate["source"],
                key,
            )
            added_ids.append(item_id)
            position += 1
            names[candidate["name"].casefold()] = connection.execute(
                "SELECT * FROM items WHERE id = ?", (item_id,)
            ).fetchone()
            by_composition[key] = names[candidate["name"].casefold()]
        return {
            "target": self._target(connection, target_type, target_id),
            "added_item_ids": added_ids,
            "unresolved_choices": unresolved,
            "conflicts": conflicts,
        }

    def include_module(
        self,
        target_type: str,
        target_id: str,
        module_id: str,
        variant: str | None = None,
        choices: Any = None,
    ) -> dict[str, Any]:
        with self._connect() as connection, connection:
            self._require_target(connection, target_type, target_id)
            module = self._module_from_connection(connection, module_id)
            selection_ids = self._add_module_selections(
                connection,
                target_type,
                target_id,
                [{"module_id": module_id, "variant": variant, "choices": choices}],
            )
            resolved, _ = self._resolve_target(connection, target_type, target_id)
            for item in resolved:
                if item["selection_id"] == selection_ids[0]:
                    connection.execute(
                        "DELETE FROM composition_exclusions "
                        "WHERE target_type = ? AND target_id = ? AND composition_key = ?",
                        (target_type, target_id, item["composition_key"]),
                    )
            result = self._materialize(connection, target_type, target_id)
            result.update(
                {
                    "module_id": module_id,
                    "module": module,
                    "selection_id": selection_ids[0],
                    "variant": variant,
                    "available_variants": [item["label"] for item in module["variants"]],
                }
            )
            return result

    def refresh_composition(self, target_type: str, target_id: str) -> dict[str, Any]:
        with self._connect() as connection, connection:
            result = self._materialize(connection, target_type, target_id)
            result["refreshed"] = True
            return result

    def select_module_option(
        self,
        target_type: str,
        target_id: str,
        choice_key: str,
        option_key: str,
        selection_id: str | None = None,
    ) -> dict[str, Any]:
        with self._connect() as connection, connection:
            self._require_target(connection, target_type, target_id)
            if selection_id is None:
                candidates = []
                for selection in connection.execute(
                    "SELECT id, module_id FROM composition_selections "
                    "WHERE target_type = ? AND target_id = ? ORDER BY position, id",
                    (target_type, target_id),
                ).fetchall():
                    module_ids = self._included_module_ids(connection, selection["module_id"])
                    placeholders = ", ".join("?" for _ in module_ids)
                    if connection.execute(
                        f"SELECT 1 FROM module_choices WHERE module_id IN ({placeholders}) "
                        "AND (choice_key = ? OR id = ?) LIMIT 1",
                        (*module_ids, choice_key, choice_key),
                    ).fetchone():
                        candidates.append(selection)
                if len(candidates) != 1:
                    raise ChecklistError(
                        "selection_id is required when the choice is not unique.",
                        details={"matching_selections": [row["id"] for row in candidates]},
                    )
                selection_id = candidates[0]["id"]
            selection = connection.execute(
                "SELECT * FROM composition_selections "
                "WHERE id = ? AND target_type = ? AND target_id = ?",
                (selection_id, target_type, target_id),
            ).fetchone()
            if selection is None:
                raise ChecklistError(f"Unknown selection id: {selection_id}.", code="not_found")
            choice_module_id, canonical_choice, canonical_option = self._validate_choice_option(
                connection, selection["module_id"], choice_key, option_key
            )
            old = connection.execute(
                "SELECT option_key FROM composition_choices "
                "WHERE selection_id = ? AND module_id = ? AND choice_key = ?",
                (selection_id, choice_module_id, canonical_choice),
            ).fetchone()
            conflicts = []
            if old and old["option_key"] != canonical_option:
                prefix = f"module:{choice_module_id}:choice:{canonical_choice}:"
                for row in connection.execute(
                    "SELECT id, edited FROM items "
                    "WHERE target_type = ? AND target_id = ? AND composition_key LIKE ?",
                    (target_type, target_id, f"{prefix}%"),
                ).fetchall():
                    if row["edited"]:
                        conflicts.append(
                            {
                                "existing_item_id": row["id"],
                                "reason": "edited_previous_choice_preserved",
                            }
                        )
                    else:
                        connection.execute("DELETE FROM items WHERE id = ?", (row["id"],))
            connection.execute(
                "DELETE FROM composition_choices "
                "WHERE selection_id = ? AND module_id = ? AND choice_key = ?",
                (selection_id, choice_module_id, canonical_choice),
            )
            connection.execute(
                "INSERT INTO composition_choices(selection_id, module_id, choice_key, option_key) "
                "VALUES (?, ?, ?, ?)",
                (selection_id, choice_module_id, canonical_choice, canonical_option),
            )
            result = self._materialize(connection, target_type, target_id)
            result.update(
                {
                    "selection_id": selection_id,
                    "choice_key": canonical_choice,
                    "option_key": canonical_option,
                }
            )
            result["conflicts"] = [*conflicts, *result["conflicts"]]
            return result
