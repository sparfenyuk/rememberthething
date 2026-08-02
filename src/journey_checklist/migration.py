from __future__ import annotations

import json
import sqlite3
from typing import TYPE_CHECKING, Any

from .module_definitions import stable_key


class LegacyPackMigrationMixin:
    if TYPE_CHECKING:

        @staticmethod
        def _id(prefix: str) -> str: ...

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

    @classmethod
    def _migrate_legacy_packs(cls, connection: sqlite3.Connection) -> None:
        """Copy the old pack graph once; keep the source tables for rollback/read-only use."""
        packs = connection.execute("SELECT * FROM packs ORDER BY id").fetchall()
        for pack in packs:
            existing = connection.execute(
                "SELECT id FROM modules WHERE legacy_pack_id = ?", (pack["id"],)
            ).fetchone()
            if existing:
                continue
            module_id = cls._id("module")
            try:
                connection.execute(
                    """INSERT INTO modules(
                        id, name, description, legacy_pack_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        module_id,
                        pack["name"],
                        pack["description"],
                        pack["id"],
                        pack["created_at"],
                        pack["updated_at"],
                    ),
                )
            except sqlite3.IntegrityError:
                suffix = f" (legacy {pack['id']})"
                module_name = f"{pack['name']}{suffix}"
                suffix_number = 2
                while connection.execute(
                    "SELECT 1 FROM modules WHERE name = ?", (module_name,)
                ).fetchone():
                    module_name = f"{pack['name']}{suffix} {suffix_number}"
                    suffix_number += 1
                connection.execute(
                    """INSERT INTO modules(
                        id, name, description, legacy_pack_id, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        module_id,
                        module_name,
                        pack["description"],
                        pack["id"],
                        pack["created_at"],
                        pack["updated_at"],
                    ),
                )
                cls._migration_diagnostic(
                    connection,
                    "pack",
                    pack["id"],
                    f"Pack name conflicted with an existing module; migrated as {module_name!r}.",
                )
            rows = connection.execute(
                "SELECT * FROM pack_items WHERE pack_id = ? ORDER BY position, id", (pack["id"],)
            ).fetchall()
            common_rows = [row for row in rows if row["variant"] is None]
            common_keys = cls._legacy_keys(common_rows, connection, pack["id"])
            for position, row in enumerate(common_rows):
                cls._insert_module_item(
                    connection,
                    module_id,
                    common_keys[row["id"]],
                    cls._legacy_item_values(row),
                    position,
                )
            by_variant: dict[str, list[sqlite3.Row]] = {}
            for row in rows:
                if row["variant"] is not None:
                    by_variant.setdefault(row["variant"], []).append(row)
            common_by_name = {row["name"].casefold(): common_keys[row["id"]] for row in common_rows}
            for variant_position, (label, variant_rows) in enumerate(by_variant.items()):
                variant_id = cls._id("variant")
                connection.execute(
                    "INSERT INTO module_variants(id, module_id, label, position) "
                    "VALUES (?, ?, ?, ?)",
                    (variant_id, module_id, label, variant_position),
                )
                variant_names = {row["name"].casefold() for row in variant_rows}
                for remove_position, row in enumerate(common_rows):
                    if row["name"].casefold() not in variant_names:
                        connection.execute(
                            "INSERT INTO module_variant_removes(variant_id, item_key, position) "
                            "VALUES (?, ?, ?)",
                            (variant_id, common_keys[row["id"]], remove_position),
                        )
                variant_keys = cls._legacy_keys(
                    variant_rows, connection, pack["id"], set(common_keys.values())
                )
                add_position = 0
                for row in variant_rows:
                    if row["name"].casefold() in common_by_name:
                        continue
                    cls._insert_variant_add(
                        connection,
                        variant_id,
                        variant_keys[row["id"]],
                        cls._legacy_item_values(row),
                        add_position,
                    )
                    add_position += 1
            cls._migrate_pack_item_provenance(connection, pack, module_id, common_keys)

    @classmethod
    def _migration_diagnostic(
        cls, connection: sqlite3.Connection, source_type: str, source_id: str, message: str
    ) -> None:
        connection.execute(
            "INSERT INTO migration_diagnostics(id, source_type, source_id, message) "
            "VALUES (?, ?, ?, ?)",
            (cls._id("migration"), source_type, source_id, message),
        )

    @classmethod
    def _legacy_keys(
        cls,
        rows: list[sqlite3.Row],
        connection: sqlite3.Connection,
        source_id: str,
        used: set[str] | None = None,
    ) -> dict[str, str]:
        result: dict[str, str] = {}
        used = set() if used is None else used
        for row in rows:
            base = stable_key(row["name"])
            key = base
            suffix = 2
            while key in used:
                key = f"{base}-{suffix}"
                suffix += 1
            if key != base:
                cls._migration_diagnostic(
                    connection,
                    "pack",
                    source_id,
                    f"Stable key collision for {row['name']!r}; used {key!r}.",
                )
            used.add(key)
            result[row["id"]] = key
        return result

    @classmethod
    def _migrate_pack_item_provenance(
        cls,
        connection: sqlite3.Connection,
        pack: sqlite3.Row,
        module_id: str,
        common_keys: dict[str, str],
    ) -> None:
        items = connection.execute(
            "SELECT * FROM items WHERE source_type = 'pack' AND source_id = ?", (pack["id"],)
        ).fetchall()
        for item in items:
            source = connection.execute(
                """SELECT mi.item_key FROM module_items mi
                   WHERE mi.module_id = ? AND lower(mi.name) = lower(?)
                   UNION ALL
                   SELECT va.item_key FROM module_variant_adds va
                   JOIN module_variants mv ON mv.id = va.variant_id
                   WHERE mv.module_id = ? AND lower(va.name) = lower(?)
                   LIMIT 1""",
                (module_id, item["name"], module_id, item["name"]),
            ).fetchone()
            if source is None:
                continue
            path = json.dumps([pack["name"]])
            connection.execute(
                """UPDATE items SET source_type = 'module', source_id = ?, source_label = ?,
                   composition_key = ?, source_path = ? WHERE id = ?""",
                (
                    module_id,
                    pack["name"],
                    f"module:{module_id}:{source['item_key']}",
                    path,
                    item["id"],
                ),
            )

    @classmethod
    def _legacy_item_values(cls, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "name": row["name"],
            "group_name": row["group_name"],
            "quantity": row["quantity"],
            "unit": row["unit"],
            "note": row["note"],
        }
