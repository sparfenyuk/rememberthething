from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING, Any

from .models import ChecklistError, ItemSource


class LegacyPackRepositoryMixin:
    if TYPE_CHECKING:

        @staticmethod
        def _id(prefix: str) -> str: ...

        @staticmethod
        def _now() -> str: ...

        @classmethod
        def _name(cls, value: Any, field: str = "name") -> str: ...

        @classmethod
        def _text(cls, value: Any, field: str, limit: int = 500) -> str | None: ...

        @classmethod
        def _pack_item_values(cls, item: dict[str, Any]) -> dict[str, Any]: ...

        @classmethod
        def _pack_from_connection(
            cls, connection: sqlite3.Connection, pack_id: str
        ) -> dict[str, Any]: ...

        @classmethod
        def _journey(cls, connection: sqlite3.Connection, journey_id: str) -> dict[str, Any]: ...

        @staticmethod
        def _require_target(
            connection: sqlite3.Connection, target_type: str, target_id: str
        ) -> None: ...

        @classmethod
        def _target(
            cls, connection: sqlite3.Connection, target_type: str, target_id: str
        ) -> dict[str, Any]: ...

        def _connect(self) -> sqlite3.Connection: ...

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

    def list_packs(self, journey_id: str | None = None) -> dict[str, Any]:
        with self._connect() as connection:
            journey = self._journey(connection, journey_id) if journey_id else None
            rows = connection.execute("SELECT * FROM packs ORDER BY name").fetchall()
            packs = []
            for row in rows:
                common_count = connection.execute(
                    "SELECT COUNT(*) FROM pack_items WHERE pack_id = ? AND variant IS NULL",
                    (row["id"],),
                ).fetchone()[0]
                variants = [
                    item[0]
                    for item in connection.execute(
                        "SELECT DISTINCT variant FROM pack_items "
                        "WHERE pack_id = ? AND variant IS NOT NULL ORDER BY variant",
                        (row["id"],),
                    ).fetchall()
                ]
                packs.append(
                    {
                        "id": row["id"],
                        "name": row["name"],
                        "description": row["description"],
                        "common_item_count": common_count,
                        "variants": variants,
                    }
                )
            result: dict[str, Any] = {"packs": packs}
            if journey:
                result["journey"] = {
                    "id": journey["id"],
                    "season": journey["context"].get("season"),
                }
            return result

    def get_pack(self, pack_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            return self._pack_from_connection(connection, pack_id)

    def create_pack(
        self,
        name: str,
        common_items: list[dict[str, Any]],
        variants: list[dict[str, Any]] | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        name = self._name(name)
        if not isinstance(common_items, list) or len(common_items) > 50:
            raise ChecklistError("common_items must contain at most 50 entries.")
        common = [self._pack_item_values(item) for item in common_items]
        variant_values = self._variant_values(variants or [])
        description = self._text(description, "description", 500)
        with self._connect() as connection, connection:
            pack_id = self._id("pack")
            try:
                connection.execute(
                    "INSERT INTO packs(id, name, description, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (pack_id, name, description, self._now(), self._now()),
                )
            except sqlite3.IntegrityError as exc:
                raise ChecklistError(
                    f"A pack named {name!r} already exists.", code="conflict"
                ) from exc
            self._insert_pack_items(connection, pack_id, common, variant_values)
            return self._pack_from_connection(connection, pack_id)

    @classmethod
    def _variant_values(cls, variants: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        if len(variants) > 20:
            raise ChecklistError("variants may contain at most 20 entries.")
        result: dict[str, list[dict[str, Any]]] = {}
        for variant in variants:
            if not isinstance(variant, dict):
                raise ChecklistError("Each variant must be an object.")
            label = cls._name(variant.get("label"), "variant label")
            if label in result:
                raise ChecklistError(f"Duplicate variant label: {label}.")
            raw_items = variant.get("items", [])
            if not isinstance(raw_items, list) or len(raw_items) > 50:
                raise ChecklistError("Each variant items list must contain at most 50 entries.")
            result[label] = [cls._pack_item_values(item) for item in raw_items]
        return result

    @classmethod
    def _insert_pack_items(
        cls,
        connection: sqlite3.Connection,
        pack_id: str,
        common: list[dict[str, Any]],
        variants: dict[str, list[dict[str, Any]]],
    ) -> None:
        position = 0
        for variant, values in [(None, common), *variants.items()]:
            for value in values:
                connection.execute(
                    """INSERT INTO pack_items(
                        id, pack_id, variant, name, group_name, quantity, unit, note, position
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        cls._id("packitem"),
                        pack_id,
                        variant,
                        value["name"],
                        value.get("group_name"),
                        value["quantity"],
                        value.get("unit"),
                        value.get("note"),
                        position,
                    ),
                )
                position += 1

    def update_pack(
        self,
        pack_id: str,
        name: str | None = None,
        description: str | None = None,
        common_items: list[dict[str, Any]] | None = None,
        variants: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        with self._connect() as connection, connection:
            current = connection.execute("SELECT * FROM packs WHERE id = ?", (pack_id,)).fetchone()
            if current is None:
                raise ChecklistError(f"Unknown pack id: {pack_id}.", code="not_found")
            updates: dict[str, Any] = {}
            if name is not None:
                updates["name"] = self._name(name)
            if description is not None:
                updates["description"] = self._text(description, "description", 500)
            if updates:
                updates["updated_at"] = self._now()
                try:
                    connection.execute(
                        f"UPDATE packs SET {', '.join(f'{key} = ?' for key in updates)} "
                        "WHERE id = ?",
                        (*updates.values(), pack_id),
                    )
                except sqlite3.IntegrityError as exc:
                    raise ChecklistError(
                        f"A pack named {name!r} already exists.", code="conflict"
                    ) from exc
            if common_items is not None or variants is not None:
                if common_items is not None and (
                    not isinstance(common_items, list) or len(common_items) > 50
                ):
                    raise ChecklistError("common_items must contain at most 50 entries.")
                common = (
                    [self._pack_item_values(item) for item in common_items]
                    if common_items is not None
                    else None
                )
                variant_values = self._variant_values(variants) if variants is not None else None
                current_items = connection.execute(
                    "SELECT * FROM pack_items WHERE pack_id = ? ORDER BY position, id", (pack_id,)
                ).fetchall()
                if common is None:
                    common = [
                        {
                            "name": row["name"],
                            "group_name": row["group_name"],
                            "quantity": row["quantity"],
                            "unit": row["unit"],
                            "note": row["note"],
                        }
                        for row in current_items
                        if row["variant"] is None
                    ]
                if variant_values is None:
                    variant_values = {}
                    for row in current_items:
                        if row["variant"] is not None:
                            variant_values.setdefault(row["variant"], []).append(
                                {
                                    "name": row["name"],
                                    "group_name": row["group_name"],
                                    "quantity": row["quantity"],
                                    "unit": row["unit"],
                                    "note": row["note"],
                                }
                            )
                connection.execute("DELETE FROM pack_items WHERE pack_id = ?", (pack_id,))
                self._insert_pack_items(connection, pack_id, common, variant_values)
            return self._pack_from_connection(connection, pack_id)

    def delete_pack(self, pack_id: str) -> dict[str, Any]:
        with self._connect() as connection, connection:
            row = connection.execute(
                "SELECT id, name FROM packs WHERE id = ?", (pack_id,)
            ).fetchone()
            if row is None:
                raise ChecklistError(f"Unknown pack id: {pack_id}.", code="not_found")
            connection.execute("DELETE FROM packs WHERE id = ?", (pack_id,))
            return {"deleted_pack_id": pack_id, "name": row["name"]}

    def include_pack(
        self, target_type: str, target_id: str, pack_id: str, variant: str | None = None
    ) -> dict[str, Any]:
        with self._connect() as connection, connection:
            self._require_target(connection, target_type, target_id)
            pack = connection.execute("SELECT * FROM packs WHERE id = ?", (pack_id,)).fetchone()
            if pack is None:
                raise ChecklistError(f"Unknown pack id: {pack_id}.", code="not_found")
            variants = [
                row[0]
                for row in connection.execute(
                    "SELECT DISTINCT variant FROM pack_items "
                    "WHERE pack_id = ? AND variant IS NOT NULL ORDER BY variant",
                    (pack_id,),
                ).fetchall()
            ]
            if variant is not None and variant not in variants:
                raise ChecklistError(
                    f"Unknown variant {variant!r}; choose one of {variants}.",
                    code="validation_error",
                    details={"available_variants": variants},
                )
            rows = connection.execute(
                "SELECT * FROM pack_items "
                "WHERE pack_id = ? AND (variant IS NULL OR variant = ?) "
                "ORDER BY position, id",
                (pack_id, variant),
            ).fetchall()
            existing = {
                row["name"].casefold(): row
                for row in connection.execute(
                    "SELECT * FROM items WHERE target_type = ? AND target_id = ?",
                    (target_type, target_id),
                ).fetchall()
            }
            conflicts = []
            added_ids = []
            position = connection.execute(
                "SELECT COALESCE(MAX(position) + 1, 0) FROM items "
                "WHERE target_type = ? AND target_id = ?",
                (target_type, target_id),
            ).fetchone()[0]
            for offset, row in enumerate(rows):
                existing_row = existing.get(row["name"].casefold())
                if existing_row:
                    conflicts.append(
                        {
                            "name": row["name"],
                            "existing_item_id": existing_row["id"],
                            "pack_item_id": row["id"],
                            "reason": "duplicate_name_preserved",
                            "edited": bool(existing_row["edited"]),
                        }
                    )
                    continue
                added_ids.append(
                    self._insert_item(
                        connection,
                        target_type,
                        target_id,
                        {
                            "name": row["name"],
                            "group_name": row["group_name"],
                            "quantity": row["quantity"],
                            "unit": row["unit"],
                            "note": row["note"],
                            "packed": False,
                            "not_needed": False,
                        },
                        position + offset,
                        ItemSource("pack", pack_id, pack["name"], variant),
                    )
                )
            return {
                "target": self._target(connection, target_type, target_id),
                "pack_id": pack_id,
                "variant": variant,
                "available_variants": variants,
                "added_item_ids": added_ids,
                "conflicts": conflicts,
            }
