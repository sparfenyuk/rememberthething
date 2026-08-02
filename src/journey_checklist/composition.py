from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any

from .models import ChecklistError
from .module_definitions import stable_key

__all__ = ["CompositionRepositoryMixin", "stable_key"]


class CompositionRepositoryMixin:
    if TYPE_CHECKING:

        @staticmethod
        def _id(prefix: str) -> str: ...

        @staticmethod
        def _now() -> str: ...

        def _connect(self) -> sqlite3.Connection: ...

        @staticmethod
        def _require_target(
            connection: sqlite3.Connection, target_type: str, target_id: str
        ) -> None: ...

        @classmethod
        def _resolve_target(
            cls, connection: sqlite3.Connection, target_type: str, target_id: str
        ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]: ...

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
    def _composition_view(
        cls, connection: sqlite3.Connection, target_type: str, target_id: str
    ) -> dict[str, Any]:
        selections = connection.execute(
            """SELECT cs.*, m.name AS module_name FROM composition_selections cs
               JOIN modules m ON m.id = cs.module_id
               WHERE cs.target_type = ? AND cs.target_id = ? ORDER BY cs.position, cs.id""",
            (target_type, target_id),
        ).fetchall()
        selected = []
        for row in selections:
            choices = [
                {
                    "module_id": choice["module_id"],
                    "choice_key": choice["choice_key"],
                    "option_key": choice["option_key"],
                }
                for choice in connection.execute(
                    "SELECT module_id, choice_key, option_key FROM composition_choices "
                    "WHERE selection_id = ? ORDER BY module_id, choice_key",
                    (row["id"],),
                ).fetchall()
            ]
            selected.append(
                {
                    "selection_id": row["id"],
                    "module_id": row["module_id"],
                    "name": row["module_name"],
                    "variant": row["variant"],
                    "position": row["position"],
                    "choices": choices,
                }
            )
        _, unresolved = cls._resolve_target(connection, target_type, target_id)
        return {"selected_modules": selected, "modules": selected, "unresolved_choices": unresolved}

    @classmethod
    def _choice_inputs(cls, raw: Any) -> list[dict[str, Any]]:
        if raw is None:
            return []
        if isinstance(raw, dict):
            return [{"choice_key": key, "option_key": value} for key, value in raw.items()]
        if not isinstance(raw, list) or len(raw) > 50:
            raise ChecklistError("choice selections must contain at most 50 entries.")
        return raw

    @classmethod
    def _add_module_selections(
        cls,
        connection: sqlite3.Connection,
        target_type: str,
        target_id: str,
        selections: list[dict[str, Any] | str],
    ) -> list[str]:
        if len(selections) > 20:
            raise ChecklistError("module_selections may contain at most 20 entries.")
        cls._require_target(connection, target_type, target_id)
        position = connection.execute(
            "SELECT COALESCE(MAX(position) + 1, 0) FROM composition_selections "
            "WHERE target_type = ? AND target_id = ?",
            (target_type, target_id),
        ).fetchone()[0]
        ids = []
        for offset, raw in enumerate(selections):
            module_id: Any
            if isinstance(raw, str):
                module_id, variant, choices = raw, None, []
            elif isinstance(raw, dict):
                module_id = raw.get("module_id", raw.get("id"))
                variant = raw.get("variant")
                choices = cls._choice_inputs(raw.get("choices", raw.get("choice_selections")))
            else:
                raise ChecklistError("Each module selection must be an object or module ID.")
            module = connection.execute(
                "SELECT * FROM modules WHERE id = ?", (module_id,)
            ).fetchone()
            if module is None:
                raise ChecklistError(f"Unknown module id: {module_id}.", code="not_found")
            if (
                variant is not None
                and connection.execute(
                    "SELECT 1 FROM module_variants WHERE module_id = ? AND label = ?",
                    (module_id, variant),
                ).fetchone()
                is None
            ):
                raise ChecklistError(f"Unknown variant {variant!r} for module {module_id}.")
            selection_id = cls._id("selection")
            connection.execute(
                "INSERT INTO composition_selections(id, target_type, target_id, module_id, "
                "variant, position) VALUES (?, ?, ?, ?, ?, ?)",
                (selection_id, target_type, target_id, module_id, variant, position + offset),
            )
            for choice in choices:
                if not isinstance(choice, dict):
                    raise ChecklistError("Each choice selection must be an object.")
                choice_key = choice.get("choice_key", choice.get("choice_id"))
                option_key = choice.get("option_key")
                if not isinstance(choice_key, str) or not isinstance(option_key, str):
                    raise ChecklistError("Choice selections require choice_key and option_key.")
                choice_module_id = choice.get("module_id")
                if choice_module_id is not None and not isinstance(choice_module_id, str):
                    raise ChecklistError("choice module_id must be a string.")
                canonical_module, canonical_choice, canonical_option = cls._validate_choice_option(
                    connection, module_id, choice_key, option_key, choice_module_id
                )
                connection.execute(
                    "INSERT INTO composition_choices("
                    "selection_id, module_id, choice_key, option_key) VALUES (?, ?, ?, ?)",
                    (selection_id, canonical_module, canonical_choice, canonical_option),
                )
            ids.append(selection_id)
        return ids

    @classmethod
    def _copy_composition(
        cls,
        connection: sqlite3.Connection,
        source_type: str,
        source_id: str,
        target_type: str,
        target_id: str,
    ) -> None:
        mapping: dict[str, str] = {}
        for row in connection.execute(
            "SELECT * FROM composition_selections "
            "WHERE target_type = ? AND target_id = ? ORDER BY position, id",
            (source_type, source_id),
        ).fetchall():
            new_id = cls._id("selection")
            mapping[row["id"]] = new_id
            connection.execute(
                "INSERT INTO composition_selections(id, target_type, target_id, module_id, "
                "variant, position) VALUES (?, ?, ?, ?, ?, ?)",
                (new_id, target_type, target_id, row["module_id"], row["variant"], row["position"]),
            )
            for choice in connection.execute(
                "SELECT module_id, choice_key, option_key FROM composition_choices "
                "WHERE selection_id = ?",
                (row["id"],),
            ).fetchall():
                connection.execute(
                    "INSERT INTO composition_choices("
                    "selection_id, module_id, choice_key, option_key) VALUES (?, ?, ?, ?)",
                    (new_id, choice["module_id"], choice["choice_key"], choice["option_key"]),
                )
        for exclusion in connection.execute(
            "SELECT composition_key FROM composition_exclusions "
            "WHERE target_type = ? AND target_id = ?",
            (source_type, source_id),
        ).fetchall():
            connection.execute(
                "INSERT OR IGNORE INTO composition_exclusions("
                "target_type, target_id, composition_key, created_at) VALUES (?, ?, ?, ?)",
                (target_type, target_id, exclusion["composition_key"], cls._now()),
            )
