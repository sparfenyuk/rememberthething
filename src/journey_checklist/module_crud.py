from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any, cast

from .models import ChecklistError


class ModuleCrudMixin:
    if TYPE_CHECKING:

        @staticmethod
        def _id(prefix: str) -> str: ...

        @staticmethod
        def _now() -> str: ...

        @classmethod
        def _name(cls, value: Any, field: str = "name") -> str: ...

        @classmethod
        def _text(cls, value: Any, field: str, limit: int = 500) -> str | None: ...

        def _connect(self) -> sqlite3.Connection: ...

        @classmethod
        def _normalize_module_items(
            cls, raw_items: Any, *, field: str, allow_missing_key: bool = True
        ) -> list[dict[str, Any]]: ...

        @classmethod
        def _normalize_variants(
            cls, raw_variants: Any, common_keys: set[str]
        ) -> list[dict[str, Any]]: ...

        @classmethod
        def _normalize_choices(cls, raw_choices: Any) -> list[dict[str, Any]]: ...

        @classmethod
        def _normalize_includes(
            cls, connection: sqlite3.Connection, raw_includes: Any
        ) -> list[str]: ...

        @classmethod
        def _assert_no_module_cycle(
            cls, connection: sqlite3.Connection, module_id: str, includes: list[str]
        ) -> None: ...

        @classmethod
        def _module_from_connection(
            cls, connection: sqlite3.Connection, module_id: str
        ) -> dict[str, Any]: ...

        @classmethod
        def _insert_module_item(
            cls,
            connection: sqlite3.Connection,
            module_id: str,
            item_key: str,
            value: dict[str, Any],
            position: int,
        ) -> None: ...

        @classmethod
        def _insert_variant_add(
            cls,
            connection: sqlite3.Connection,
            variant_id: str,
            item_key: str,
            value: dict[str, Any],
            position: int,
        ) -> None: ...

    def list_modules(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            modules = []
            for row in connection.execute("SELECT * FROM modules ORDER BY name, id").fetchall():
                modules.append(
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "description": row["description"],
                        "common_item_count": connection.execute(
                            "SELECT COUNT(*) FROM module_items WHERE module_id = ?", (row["id"],)
                        ).fetchone()[0],
                        "variants": [
                            item[0]
                            for item in connection.execute(
                                "SELECT label FROM module_variants "
                                "WHERE module_id = ? ORDER BY position, id",
                                (row["id"],),
                            ).fetchall()
                        ],
                        "include_count": connection.execute(
                            "SELECT COUNT(*) FROM module_includes WHERE module_id = ?", (row["id"],)
                        ).fetchone()[0],
                        "choice_count": connection.execute(
                            "SELECT COUNT(*) FROM module_choices WHERE module_id = ?", (row["id"],)
                        ).fetchone()[0],
                    }
                )
            return modules

    def get_module(self, module_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            return self._module_from_connection(connection, module_id)

    def create_module(
        self,
        name: str,
        common_items: list[dict[str, Any]] | None = None,
        variants: list[dict[str, Any]] | None = None,
        includes: list[dict[str, Any] | str] | None = None,
        choices: list[dict[str, Any]] | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        name = self._name(name)
        common = self._normalize_module_items(common_items or [], field="common_items")
        variant_values = self._normalize_variants(
            variants or [], {item["item_key"] for item in common}
        )
        choice_values = self._normalize_choices(choices or [])
        description = self._text(description, "description", 500)
        with self._connect() as connection, connection:
            module_id = self._id("module")
            include_ids = self._normalize_includes(connection, includes or [])
            self._assert_no_module_cycle(connection, module_id, include_ids)
            try:
                connection.execute(
                    "INSERT INTO modules(id, name, description, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (module_id, name, description, self._now(), self._now()),
                )
            except sqlite3.IntegrityError as exc:
                raise ChecklistError(
                    f"A module named {name!r} already exists.", code="conflict"
                ) from exc
            self._write_module_children(
                connection, module_id, common, variant_values, include_ids, choice_values
            )
            return self._module_from_connection(connection, module_id)

    @classmethod
    def _write_module_children(
        cls,
        connection: sqlite3.Connection,
        module_id: str,
        common: list[dict[str, Any]],
        variants: list[dict[str, Any]],
        includes: list[str],
        choices: list[dict[str, Any]],
    ) -> None:
        for position, item in enumerate(common):
            cls._insert_module_item(connection, module_id, item["item_key"], item, position)
        for position, variant in enumerate(variants):
            variant_id = cls._id("variant")
            connection.execute(
                "INSERT INTO module_variants(id, module_id, label, position) VALUES (?, ?, ?, ?)",
                (variant_id, module_id, variant["label"], position),
            )
            for add_position, item in enumerate(variant["add"]):
                cls._insert_variant_add(
                    connection, variant_id, item["item_key"], item, add_position
                )
            for remove_position, item_key in enumerate(variant["remove"]):
                connection.execute(
                    "INSERT INTO module_variant_removes(variant_id, item_key, position) "
                    "VALUES (?, ?, ?)",
                    (variant_id, item_key, remove_position),
                )
        for position, included_module_id in enumerate(includes):
            connection.execute(
                "INSERT INTO module_includes(id, module_id, included_module_id, position) "
                "VALUES (?, ?, ?, ?)",
                (cls._id("include"), module_id, included_module_id, position),
            )
        for position, choice in enumerate(choices):
            choice_id = cls._id("choice")
            connection.execute(
                "INSERT INTO module_choices(id, module_id, choice_key, label, required, position) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    choice_id,
                    module_id,
                    choice["choice_key"],
                    choice["label"],
                    int(choice["required"]),
                    position,
                ),
            )
            for option_position, option in enumerate(choice["options"]):
                connection.execute(
                    """INSERT INTO module_choice_options(
                        id, choice_id, option_key, name, group_name, quantity, unit, note, position
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        cls._id("option"),
                        choice_id,
                        option["option_key"],
                        option["name"],
                        option.get("group_name"),
                        option["quantity"],
                        option.get("unit"),
                        option.get("note"),
                        option_position,
                    ),
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
        with self._connect() as connection, connection:
            current = self._module_from_connection(connection, module_id)
            common = (
                self._normalize_module_items(common_items, field="common_items")
                if common_items is not None
                else [dict(item, item_key=item["item_key"]) for item in current["items"]]
            )
            common_keys = {item["item_key"] for item in common}
            old_variants = current["variants"]
            variant_values = self._normalize_variants(
                variants if variants is not None else old_variants, common_keys
            )
            choice_values = self._normalize_choices(
                choices if choices is not None else current["choices"]
            )
            include_ids = self._normalize_includes(
                connection,
                includes
                if includes is not None
                else [item["module_id"] for item in current["includes"]],
            )
            self._assert_no_module_cycle(connection, module_id, include_ids)
            updates: dict[str, Any] = {}
            if name is not None:
                updates["name"] = self._name(name)
            if description is not None:
                updates["description"] = self._text(description, "description", 500)
            if updates:
                updates["updated_at"] = self._now()
                try:
                    connection.execute(
                        f"UPDATE modules SET {', '.join(f'{key} = ?' for key in updates)} "
                        "WHERE id = ?",
                        (*updates.values(), module_id),
                    )
                except sqlite3.IntegrityError as exc:
                    raise ChecklistError(
                        f"A module named {name!r} already exists.", code="conflict"
                    ) from exc
            if (
                common_items is not None
                or variants is not None
                or includes is not None
                or choices is not None
            ):
                connection.execute("DELETE FROM module_items WHERE module_id = ?", (module_id,))
                connection.execute("DELETE FROM module_variants WHERE module_id = ?", (module_id,))
                connection.execute("DELETE FROM module_includes WHERE module_id = ?", (module_id,))
                connection.execute("DELETE FROM module_choices WHERE module_id = ?", (module_id,))
                self._write_module_children(
                    connection, module_id, common, variant_values, include_ids, choice_values
                )
            return self._module_from_connection(connection, module_id)

    def delete_module(self, module_id: str) -> dict[str, Any]:
        with self._connect() as connection, connection:
            row = connection.execute(
                "SELECT id, name FROM modules WHERE id = ?", (module_id,)
            ).fetchone()
            if row is None:
                raise ChecklistError(f"Unknown module id: {module_id}.", code="not_found")
            referenced = connection.execute(
                """SELECT 1 FROM module_includes WHERE included_module_id = ?
                   UNION ALL SELECT 1 FROM composition_selections WHERE module_id = ? LIMIT 1""",
                (module_id, module_id),
            ).fetchone()
            if referenced:
                raise ChecklistError(
                    f"Module {module_id} is still used by a composition.",
                    code="conflict",
                )
            connection.execute("DELETE FROM modules WHERE id = ?", (module_id,))
            return {"deleted_module_id": module_id, "name": row["name"]}

    @classmethod
    def _choice_record(
        cls, connection: sqlite3.Connection, module_id: str, choice_key: str
    ) -> sqlite3.Row:
        row = connection.execute(
            "SELECT * FROM module_choices WHERE module_id = ? AND (choice_key = ? OR id = ?)",
            (module_id, choice_key, choice_key),
        ).fetchone()
        if row is None:
            raise ChecklistError(
                f"Unknown choice {choice_key!r} for module {module_id}.", code="not_found"
            )
        return cast(sqlite3.Row, row)

    @classmethod
    def _validate_choice_option(
        cls, connection: sqlite3.Connection, module_id: str, choice_key: str, option_key: str
    ) -> tuple[str, str]:
        choice = cls._choice_record(connection, module_id, choice_key)
        option = connection.execute(
            "SELECT option_key FROM module_choice_options WHERE choice_id = ? AND option_key = ?",
            (choice["id"], option_key),
        ).fetchone()
        if option is None:
            available = [
                item[0]
                for item in connection.execute(
                    "SELECT option_key FROM module_choice_options "
                    "WHERE choice_id = ? ORDER BY position, id",
                    (choice["id"],),
                ).fetchall()
            ]
            raise ChecklistError(
                f"Unknown option {option_key!r}; choose one of {available}.",
                details={"available_options": available},
            )
        return choice["choice_key"], option["option_key"]
