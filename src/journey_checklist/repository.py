from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from .composition import CompositionRepositoryMixin
from .legacy_packs import LegacyPackRepositoryMixin
from .materialization import MaterializationMixin
from .migration import LegacyPackMigrationMixin
from .models import ChecklistError, ItemSource
from .module_crud import ModuleCrudMixin
from .module_definitions import ModuleDefinitionMixin

TargetType = Literal["journey", "blueprint"]


class Repository(
    CompositionRepositoryMixin,
    MaterializationMixin,
    ModuleCrudMixin,
    ModuleDefinitionMixin,
    LegacyPackRepositoryMixin,
    LegacyPackMigrationMixin,
):
    """Small transactional SQLite repository for the snapshot-based domain."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def initialize(self) -> None:
        with self._connect() as connection:
            self._schema(connection)

    def ready(self) -> tuple[bool, str]:
        try:
            self.initialize()
            return True, "ok"
        except (OSError, sqlite3.Error, ChecklistError) as exc:
            return False, str(exc)

    def _connect(self) -> sqlite3.Connection:
        if str(self.path) == ":memory:":
            raise ChecklistError("An on-disk SQLite path is required.", code="storage_unavailable")
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            if not self.path.parent.is_dir():
                raise ChecklistError(
                    "SQLite storage parent is not a directory.", code="storage_unavailable"
                )
            connection = sqlite3.connect(self.path, timeout=10)
        except OSError as exc:
            raise ChecklistError(
                f"SQLite storage is unavailable: {exc}", code="storage_unavailable"
            ) from exc
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        self._schema(connection)
        return connection

    @classmethod
    def _schema(cls, connection: sqlite3.Connection) -> None:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS blueprints (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS journeys (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                destination TEXT,
                purpose TEXT,
                start_date TEXT,
                end_date TEXT,
                duration_days INTEGER,
                season TEXT,
                source_blueprint_id TEXT REFERENCES blueprints(id),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS packs (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pack_items (
                id TEXT PRIMARY KEY,
                pack_id TEXT NOT NULL REFERENCES packs(id) ON DELETE CASCADE,
                variant TEXT,
                name TEXT NOT NULL,
                group_name TEXT,
                quantity INTEGER NOT NULL DEFAULT 1,
                unit TEXT,
                note TEXT,
                position INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS items (
                id TEXT PRIMARY KEY,
                target_type TEXT NOT NULL CHECK (target_type IN ('journey', 'blueprint')),
                target_id TEXT NOT NULL,
                name TEXT NOT NULL,
                group_name TEXT,
                quantity INTEGER NOT NULL DEFAULT 1,
                unit TEXT,
                note TEXT,
                packed INTEGER NOT NULL DEFAULT 0,
                not_needed INTEGER NOT NULL DEFAULT 0,
                source_type TEXT NOT NULL,
                source_id TEXT,
                source_label TEXT,
                source_variant TEXT,
                edited INTEGER NOT NULL DEFAULT 0,
                position INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS items_target_idx ON items(target_type, target_id, position);
            CREATE INDEX IF NOT EXISTS pack_items_pack_idx ON pack_items(pack_id, variant, position);

            CREATE TABLE IF NOT EXISTS modules (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                legacy_pack_id TEXT UNIQUE,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS module_items (
                id TEXT PRIMARY KEY,
                module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
                item_key TEXT NOT NULL,
                name TEXT NOT NULL,
                group_name TEXT,
                quantity INTEGER NOT NULL DEFAULT 1,
                unit TEXT,
                note TEXT,
                position INTEGER NOT NULL DEFAULT 0,
                UNIQUE(module_id, item_key)
            );
            CREATE TABLE IF NOT EXISTS module_variants (
                id TEXT PRIMARY KEY,
                module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
                label TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                UNIQUE(module_id, label)
            );
            CREATE TABLE IF NOT EXISTS module_variant_adds (
                id TEXT PRIMARY KEY,
                variant_id TEXT NOT NULL REFERENCES module_variants(id) ON DELETE CASCADE,
                item_key TEXT NOT NULL,
                name TEXT NOT NULL,
                group_name TEXT,
                quantity INTEGER NOT NULL DEFAULT 1,
                unit TEXT,
                note TEXT,
                position INTEGER NOT NULL DEFAULT 0,
                UNIQUE(variant_id, item_key)
            );
            CREATE TABLE IF NOT EXISTS module_variant_removes (
                variant_id TEXT NOT NULL REFERENCES module_variants(id) ON DELETE CASCADE,
                item_key TEXT NOT NULL,
                position INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(variant_id, item_key)
            );
            CREATE TABLE IF NOT EXISTS module_includes (
                id TEXT PRIMARY KEY,
                module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
                included_module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE RESTRICT,
                position INTEGER NOT NULL DEFAULT 0,
                UNIQUE(module_id, included_module_id, position)
            );
            CREATE TABLE IF NOT EXISTS module_choices (
                id TEXT PRIMARY KEY,
                module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE CASCADE,
                choice_key TEXT NOT NULL,
                label TEXT NOT NULL,
                required INTEGER NOT NULL DEFAULT 1,
                position INTEGER NOT NULL DEFAULT 0,
                UNIQUE(module_id, choice_key)
            );
            CREATE TABLE IF NOT EXISTS module_choice_options (
                id TEXT PRIMARY KEY,
                choice_id TEXT NOT NULL REFERENCES module_choices(id) ON DELETE CASCADE,
                option_key TEXT NOT NULL,
                name TEXT NOT NULL,
                group_name TEXT,
                quantity INTEGER NOT NULL DEFAULT 1,
                unit TEXT,
                note TEXT,
                position INTEGER NOT NULL DEFAULT 0,
                UNIQUE(choice_id, option_key)
            );
            CREATE TABLE IF NOT EXISTS composition_selections (
                id TEXT PRIMARY KEY,
                target_type TEXT NOT NULL CHECK (target_type IN ('journey', 'blueprint')),
                target_id TEXT NOT NULL,
                module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE RESTRICT,
                variant TEXT,
                position INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS composition_selections_target_idx
                ON composition_selections(target_type, target_id, position);
            CREATE TABLE IF NOT EXISTS composition_choices (
                selection_id TEXT NOT NULL REFERENCES composition_selections(id) ON DELETE CASCADE,
                module_id TEXT NOT NULL REFERENCES modules(id) ON DELETE RESTRICT,
                choice_key TEXT NOT NULL,
                option_key TEXT NOT NULL,
                PRIMARY KEY(selection_id, module_id, choice_key)
            );
            CREATE TABLE IF NOT EXISTS composition_exclusions (
                target_type TEXT NOT NULL CHECK (target_type IN ('journey', 'blueprint')),
                target_id TEXT NOT NULL,
                composition_key TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(target_type, target_id, composition_key)
            );
            CREATE TABLE IF NOT EXISTS migration_diagnostics (
                id TEXT PRIMARY KEY,
                source_type TEXT NOT NULL,
                source_id TEXT NOT NULL,
                message TEXT NOT NULL,
                details TEXT
            );
            """
        )
        columns = {row[1] for row in connection.execute("PRAGMA table_info(items)").fetchall()}
        if "composition_key" not in columns:
            connection.execute("ALTER TABLE items ADD COLUMN composition_key TEXT")
        if "source_path" not in columns:
            connection.execute("ALTER TABLE items ADD COLUMN source_path TEXT")
        connection.execute(
            "CREATE INDEX IF NOT EXISTS items_composition_idx ON items(target_type, target_id, composition_key)"
        )
        cls._migrate_legacy_packs(connection)

    @staticmethod
    def _id(prefix: str) -> str:
        return f"{prefix}_{uuid.uuid4().hex[:12]}"

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _text(value: Any, field: str, limit: int = 500) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            raise ChecklistError(f"{field} must be a string.")
        value = value.strip()
        if len(value) > limit:
            raise ChecklistError(f"{field} must be at most {limit} characters.")
        return value or None

    @classmethod
    def _name(cls, value: Any, field: str = "name") -> str:
        name = cls._text(value, field, 200)
        if not name:
            raise ChecklistError(f"{field} is required.")
        return name

    @staticmethod
    def _quantity(value: Any) -> int:
        if isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 9999:
            raise ChecklistError("quantity must be an integer from 1 to 9999.")
        return int(value)

    @classmethod
    def _item_values(cls, item: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ChecklistError("Each item must be an object.")
        return {
            "name": cls._name(item.get("name"), "item name"),
            "group_name": cls._text(item.get("group", item.get("group_name")), "group", 100),
            "quantity": cls._quantity(item.get("quantity", 1)),
            "unit": cls._text(item.get("unit"), "unit", 40),
            "note": cls._text(item.get("note"), "note", 500),
            "packed": int(bool(item.get("packed", False))),
            "not_needed": int(bool(item.get("not_needed", False))),
        }

    @classmethod
    def _pack_item_values(cls, item: dict[str, Any]) -> dict[str, Any]:
        values = cls._item_values(item)
        if values["packed"] or values["not_needed"]:
            raise ChecklistError("Pack items cannot have journey state.")
        values.pop("packed")
        values.pop("not_needed")
        return values

    @staticmethod
    def _source(row: sqlite3.Row) -> ItemSource:
        raw_path = row["source_path"] if "source_path" in row.keys() else None
        try:
            path = tuple(json.loads(raw_path)) if raw_path else ()
        except (TypeError, ValueError):
            path = ()
        return ItemSource(
            row["source_type"],
            row["source_id"],
            row["source_label"],
            row["source_variant"],
            path,
        )

    @classmethod
    def _item_view(cls, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "group": row["group_name"],
            "quantity": row["quantity"],
            "unit": row["unit"],
            "note": row["note"],
            "packed": bool(row["packed"]),
            "not_needed": bool(row["not_needed"]),
            "source": cls._source(row).as_dict(),
            "edited": bool(row["edited"]),
        }

    @classmethod
    def _pack_item_view(cls, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": row["id"],
            "name": row["name"],
            "group": row["group_name"],
            "quantity": row["quantity"],
            "unit": row["unit"],
            "note": row["note"],
        }

    @staticmethod
    def _require_target(connection: sqlite3.Connection, target_type: str, target_id: str) -> None:
        if target_type == "journey":
            table = "journeys"
        elif target_type == "blueprint":
            table = "blueprints"
        else:
            raise ChecklistError("target_type must be journey or blueprint.")
        row = connection.execute(f"SELECT id FROM {table} WHERE id = ?", (target_id,)).fetchone()
        if row is None:
            raise ChecklistError(f"Unknown {target_type} id: {target_id}.", code="not_found")

    @classmethod
    def _items(
        cls, connection: sqlite3.Connection, target_type: str, target_id: str
    ) -> list[dict[str, Any]]:
        rows = connection.execute(
            "SELECT * FROM items WHERE target_type = ? AND target_id = ? ORDER BY position, created_at",
            (target_type, target_id),
        ).fetchall()
        return [cls._item_view(row) for row in rows]

    @classmethod
    def _blueprint(cls, connection: sqlite3.Connection, blueprint_id: str) -> dict[str, Any]:
        row = connection.execute(
            "SELECT * FROM blueprints WHERE id = ?", (blueprint_id,)
        ).fetchone()
        if row is None:
            raise ChecklistError(f"Unknown blueprint id: {blueprint_id}.", code="not_found")
        items = cls._items(connection, "blueprint", blueprint_id)
        composition = cls._composition_view(connection, "blueprint", blueprint_id)
        return {
            "id": row["id"],
            "name": row["name"],
            "items": items,
            "item_count": len(items),
            "extras": [item for item in items if item["source"]["kind"] == "direct"],
            **composition,
        }

    @classmethod
    def _pack_from_connection(cls, connection: sqlite3.Connection, pack_id: str) -> dict[str, Any]:
        row = connection.execute("SELECT * FROM packs WHERE id = ?", (pack_id,)).fetchone()
        if row is None:
            raise ChecklistError(f"Unknown pack id: {pack_id}.", code="not_found")
        items = connection.execute(
            "SELECT * FROM pack_items WHERE pack_id = ? ORDER BY position, id", (pack_id,)
        ).fetchall()
        variants: dict[str, list[dict[str, Any]]] = {}
        common = []
        for item in items:
            if item["variant"] is None:
                common.append(cls._pack_item_view(item))
            else:
                variants.setdefault(item["variant"], []).append(cls._pack_item_view(item))
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row["description"],
            "common": common,
            "variants": variants,
        }

    @classmethod
    def _journey(cls, connection: sqlite3.Connection, journey_id: str) -> dict[str, Any]:
        row = connection.execute("SELECT * FROM journeys WHERE id = ?", (journey_id,)).fetchone()
        if row is None:
            raise ChecklistError(f"Unknown journey id: {journey_id}.", code="not_found")
        items = cls._items(connection, "journey", journey_id)
        context = {
            key: row[key]
            for key in (
                "destination",
                "purpose",
                "start_date",
                "end_date",
                "duration_days",
                "season",
            )
            if row[key] is not None
        }
        return {
            "id": row["id"],
            "name": row["name"],
            "context": context,
            "source_blueprint_id": row["source_blueprint_id"],
            "items": items,
            "item_count": len(items),
            "remaining_count": sum(not item["packed"] and not item["not_needed"] for item in items),
            "extras": [item for item in items if item["source"]["kind"] in {"direct", "blueprint"}],
            **cls._composition_view(connection, "journey", journey_id),
        }

    def list_blueprints(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM blueprints ORDER BY name").fetchall()
            return [
                {
                    "id": row["id"],
                    "name": row["name"],
                    "item_count": connection.execute(
                        "SELECT COUNT(*) FROM items WHERE target_type = 'blueprint' AND target_id = ?",
                        (row["id"],),
                    ).fetchone()[0],
                }
                for row in rows
            ]

    def get_blueprint(self, blueprint_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            return self._blueprint(connection, blueprint_id)

    def create_blueprint(
        self,
        name: str,
        items: list[dict[str, Any]] | None = None,
        module_selections: list[dict[str, Any] | str] | None = None,
    ) -> dict[str, Any]:
        name = self._name(name)
        if items is None:
            items = []
        if not isinstance(items, list) or len(items) > 50:
            raise ChecklistError("items must contain at most 50 entries.")
        values = [self._item_values(item) for item in items]
        with self._connect() as connection, connection:
            blueprint_id = self._id("bp")
            try:
                connection.execute(
                    "INSERT INTO blueprints(id, name, created_at) VALUES (?, ?, ?)",
                    (blueprint_id, name, self._now()),
                )
            except sqlite3.IntegrityError as exc:
                raise ChecklistError(
                    f"A blueprint named {name!r} already exists.", code="conflict"
                ) from exc
            for position, value in enumerate(values):
                self._insert_item(
                    connection, "blueprint", blueprint_id, value, position, ItemSource("direct")
                )
            self._add_module_selections(
                connection, "blueprint", blueprint_id, module_selections or []
            )
            materialized = self._materialize(connection, "blueprint", blueprint_id)
            blueprint = self._blueprint(connection, blueprint_id)
            blueprint["conflicts"] = materialized["conflicts"]
            return blueprint

    def start_journey(
        self,
        name: str,
        context: dict[str, Any] | None = None,
        blueprint_id: str | None = None,
        module_selections: list[dict[str, Any] | str] | None = None,
    ) -> dict[str, Any]:
        name = self._name(name)
        context = self._context_values(context or {})
        with self._connect() as connection, connection:
            blueprint = self._blueprint(connection, blueprint_id) if blueprint_id else None
            journey_id = self._id("journey")
            now = self._now()
            connection.execute(
                """INSERT INTO journeys(
                    id, name, destination, purpose, start_date, end_date, duration_days, season,
                    source_blueprint_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    journey_id,
                    name,
                    context.get("destination"),
                    context.get("purpose"),
                    context.get("start_date"),
                    context.get("end_date"),
                    context.get("duration_days"),
                    context.get("season"),
                    blueprint_id,
                    now,
                    now,
                ),
            )
            if blueprint:
                assert blueprint_id is not None
                rows = connection.execute(
                    "SELECT * FROM items WHERE target_type = 'blueprint' AND target_id = ? ORDER BY position, created_at",
                    (blueprint_id,),
                ).fetchall()
                for position, row in enumerate(rows):
                    self._insert_item(
                        connection,
                        "journey",
                        journey_id,
                        {
                            "name": row["name"],
                            "group_name": row["group_name"],
                            "quantity": row["quantity"],
                            "unit": row["unit"],
                            "note": row["note"],
                            "packed": False,
                            "not_needed": False,
                        },
                        position,
                        self._source(row)
                        if row["source_type"] == "module"
                        else ItemSource("blueprint", blueprint_id, blueprint["name"]),
                        row["composition_key"],
                    )
                self._copy_composition(connection, "blueprint", blueprint_id, "journey", journey_id)
            self._add_module_selections(connection, "journey", journey_id, module_selections or [])
            materialized = self._materialize(connection, "journey", journey_id)
            journey = self._journey(connection, journey_id)
            journey["conflicts"] = materialized["conflicts"]
            return journey

    @classmethod
    def _context_values(cls, context: dict[str, Any]) -> dict[str, Any]:
        allowed = {"destination", "purpose", "start_date", "end_date", "season"}
        unknown = set(context) - allowed - {"duration_days"}
        if unknown:
            raise ChecklistError(f"Unknown journey context fields: {sorted(unknown)}.")
        values = {key: cls._text(context.get(key), key, 120) for key in allowed}
        duration = context.get("duration_days")
        if duration is not None:
            if (
                isinstance(duration, bool)
                or not isinstance(duration, int)
                or not 1 <= duration <= 3650
            ):
                raise ChecklistError("duration_days must be an integer from 1 to 3650.")
        values["duration_days"] = duration
        return values

    def get_journey(self, journey_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            return self._journey(connection, journey_id)

    def update_journey(self, journey_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "name",
            "destination",
            "purpose",
            "start_date",
            "end_date",
            "duration_days",
            "season",
        }
        if set(updates) - allowed:
            raise ChecklistError(f"Unknown journey fields: {sorted(set(updates) - allowed)}.")
        with self._connect() as connection, connection:
            self._journey(connection, journey_id)
            values: dict[str, Any] = {}
            if "name" in updates:
                values["name"] = self._name(updates["name"])
            context = {key: updates[key] for key in allowed - {"name"} if key in updates}
            validated_context = self._context_values(context)
            values.update({key: validated_context[key] for key in context})
            if not values:
                return self._journey(connection, journey_id)
            values["updated_at"] = self._now()
            assignments = ", ".join(f"{key} = ?" for key in values)
            connection.execute(
                f"UPDATE journeys SET {assignments} WHERE id = ?",
                (*values.values(), journey_id),
            )
            return self._journey(connection, journey_id)

    def add_items(
        self, target_type: str, target_id: str, items: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if not items or len(items) > 50:
            raise ChecklistError("items must contain between 1 and 50 entries.")
        values = [self._item_values(item) for item in items]
        with self._connect() as connection, connection:
            self._require_target(connection, target_type, target_id)
            position = connection.execute(
                "SELECT COALESCE(MAX(position) + 1, 0) FROM items WHERE target_type = ? AND target_id = ?",
                (target_type, target_id),
            ).fetchone()[0]
            source = ItemSource("direct", target_id if target_type == "journey" else None)
            ids = []
            for offset, value in enumerate(values):
                ids.append(
                    self._insert_item(
                        connection, target_type, target_id, value, position + offset, source
                    )
                )
            return {"target": self._target(connection, target_type, target_id), "item_ids": ids}

    def _insert_item(
        self,
        connection: sqlite3.Connection,
        target_type: str,
        target_id: str,
        value: dict[str, Any],
        position: int,
        source: ItemSource,
        composition_key: str | None = None,
    ) -> str:
        item_id = self._id("item")
        now = self._now()
        connection.execute(
            """INSERT INTO items(
                id, target_type, target_id, name, group_name, quantity, unit, note, packed, not_needed,
                source_type, source_id, source_label, source_variant, composition_key, source_path,
                edited, position, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item_id,
                target_type,
                target_id,
                value["name"],
                value.get("group_name"),
                value["quantity"],
                value.get("unit"),
                value.get("note"),
                value.get("packed", 0),
                value.get("not_needed", 0),
                source.kind,
                source.source_id,
                source.label,
                source.variant,
                composition_key,
                json.dumps(list(source.path)) if source.path else None,
                0,
                position,
                now,
                now,
            ),
        )
        return item_id

    @classmethod
    def _target(
        cls, connection: sqlite3.Connection, target_type: str, target_id: str
    ) -> dict[str, Any]:
        if target_type == "journey":
            return cls._journey(connection, target_id)
        if target_type == "blueprint":
            return cls._blueprint(connection, target_id)
        raise ChecklistError("target_type must be journey or blueprint.")

    def update_items(
        self, target_type: str, target_id: str, updates: list[dict[str, Any]]
    ) -> dict[str, Any]:
        if not updates or len(updates) > 50:
            raise ChecklistError("updates must contain between 1 and 50 entries.")
        allowed = {
            "name",
            "group",
            "group_name",
            "quantity",
            "unit",
            "note",
            "packed",
            "not_needed",
        }
        with self._connect() as connection, connection:
            self._require_target(connection, target_type, target_id)
            item_rows: dict[str, sqlite3.Row] = {}
            for update in updates:
                item_id = update.get("item_id", update.get("id"))
                if not isinstance(item_id, str) or not item_id:
                    raise ChecklistError("Each item update requires item_id.")
                if item_id in item_rows:
                    raise ChecklistError(f"Item id may appear only once per update: {item_id}.")
                row = connection.execute(
                    "SELECT * FROM items WHERE id = ? AND target_type = ? AND target_id = ?",
                    (item_id, target_type, target_id),
                ).fetchone()
                if row is None:
                    raise ChecklistError(f"Unknown item id: {item_id}.", code="not_found")
                item_rows[item_id] = row
                fields = set(update) - {"item_id", "id"}
                if not fields or fields - allowed:
                    raise ChecklistError(
                        f"Invalid fields for item {item_id}: {sorted(fields - allowed)}."
                    )
                candidate = dict(row)
                for field, value in update.items():
                    if field in {"item_id", "id"}:
                        continue
                    normalized = self._item_values({**candidate, field: value})
                    candidate.update(normalized)
                if candidate["packed"] and candidate["not_needed"]:
                    raise ChecklistError("An item cannot be both packed and not_needed.")
            for update in updates:
                item_id = update.get("item_id", update.get("id"))
                if not isinstance(item_id, str) or not item_id:
                    raise ChecklistError("Each item update requires item_id.")
                assignments: dict[str, Any] = {}
                for field, value in update.items():
                    if field in {"item_id", "id"}:
                        continue
                    column = "group_name" if field == "group" else field
                    if field in {"name", "group", "group_name", "quantity", "unit", "note"}:
                        normalized = self._item_values({**dict(item_rows[item_id]), field: value})
                        assignments[column] = normalized[
                            "group_name" if field in {"group", "group_name"} else field
                        ]
                    else:
                        assignments[column] = int(bool(value))
                assignments["edited"] = 1
                assignments["updated_at"] = self._now()
                connection.execute(
                    f"UPDATE items SET {', '.join(f'{key} = ?' for key in assignments)} WHERE id = ?",
                    (*assignments.values(), item_id),
                )
            return {
                "target": self._target(connection, target_type, target_id),
                "item_ids": list(item_rows),
            }

    def remove_items(self, target_type: str, target_id: str, item_ids: list[str]) -> dict[str, Any]:
        if not item_ids or len(item_ids) > 50:
            raise ChecklistError("item_ids must contain between 1 and 50 entries.")
        with self._connect() as connection, connection:
            self._require_target(connection, target_type, target_id)
            unique_ids = list(dict.fromkeys(item_ids))
            placeholders = ",".join("?" for _ in unique_ids)
            rows = connection.execute(
                f"SELECT id, composition_key FROM items WHERE target_type = ? AND target_id = ? AND id IN ({placeholders})",
                (target_type, target_id, *unique_ids),
            ).fetchall()
            found = {row["id"] for row in rows}
            missing = [item_id for item_id in unique_ids if item_id not in found]
            if missing:
                raise ChecklistError(f"Unknown item id(s): {missing}.", code="not_found")
            for row in rows:
                if row["composition_key"]:
                    connection.execute(
                        "INSERT OR IGNORE INTO composition_exclusions(target_type, target_id, composition_key, created_at) VALUES (?, ?, ?, ?)",
                        (target_type, target_id, row["composition_key"], self._now()),
                    )
            connection.execute(
                f"DELETE FROM items WHERE target_type = ? AND target_id = ? AND id IN ({placeholders})",
                (target_type, target_id, *unique_ids),
            )
            return {
                "target": self._target(connection, target_type, target_id),
                "removed_item_ids": unique_ids,
            }

    def promote_items(
        self,
        journey_id: str,
        item_ids: list[str],
        blueprint_id: str | None = None,
        new_blueprint_name: str | None = None,
    ) -> dict[str, Any]:
        if bool(blueprint_id) == bool(new_blueprint_name):
            raise ChecklistError("Provide exactly one of blueprint_id or new_blueprint_name.")
        if not item_ids or len(item_ids) > 50:
            raise ChecklistError("item_ids must contain between 1 and 50 entries.")
        with self._connect() as connection, connection:
            journey = self._journey(connection, journey_id)
            if blueprint_id:
                self._blueprint(connection, blueprint_id)
            else:
                name = self._name(new_blueprint_name, "new_blueprint_name")
                blueprint_id = self._id("bp")
                try:
                    connection.execute(
                        "INSERT INTO blueprints(id, name, created_at) VALUES (?, ?, ?)",
                        (blueprint_id, name, self._now()),
                    )
                except sqlite3.IntegrityError as exc:
                    raise ChecklistError(
                        f"A blueprint named {name!r} already exists.", code="conflict"
                    ) from exc
            unique_ids = list(dict.fromkeys(item_ids))
            placeholders = ",".join("?" for _ in unique_ids)
            rows = connection.execute(
                f"SELECT * FROM items WHERE target_type = 'journey' AND target_id = ? AND id IN ({placeholders})",
                (journey_id, *unique_ids),
            ).fetchall()
            by_id = {row["id"]: row for row in rows}
            missing = [item_id for item_id in unique_ids if item_id not in by_id]
            if missing:
                raise ChecklistError(f"Unknown item id(s): {missing}.", code="not_found")
            non_direct = [
                item_id for item_id in unique_ids if by_id[item_id]["source_type"] != "direct"
            ]
            if non_direct:
                raise ChecklistError(
                    f"Only direct journey items can be promoted: {non_direct}.",
                    code="validation_error",
                )
            existing_names = {
                row["name"].casefold()
                for row in connection.execute(
                    "SELECT name FROM items WHERE target_type = 'blueprint' AND target_id = ?",
                    (blueprint_id,),
                ).fetchall()
            }
            promoted_ids = []
            skipped = []
            position = connection.execute(
                "SELECT COALESCE(MAX(position) + 1, 0) FROM items WHERE target_type = 'blueprint' AND target_id = ?",
                (blueprint_id,),
            ).fetchone()[0]
            for offset, item_id in enumerate(unique_ids):
                row = by_id[item_id]
                if row["name"].casefold() in existing_names:
                    skipped.append(
                        {"item_id": item_id, "name": row["name"], "reason": "duplicate_name"}
                    )
                    continue
                promoted_ids.append(
                    self._insert_item(
                        connection,
                        "blueprint",
                        blueprint_id,
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
                        ItemSource("journey", journey_id, journey["name"]),
                    )
                )
            return {
                "blueprint": self._blueprint(connection, blueprint_id),
                "journey": self._journey(connection, journey_id),
                "promoted_item_ids": promoted_ids,
                "skipped": skipped,
            }
