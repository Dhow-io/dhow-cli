"""Metadata compiler: DocType classes → registry / migrations / schemas / manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dhow.core.doctype import DocType
from dhow.core.registry import DocTypeEntry, Registry
from dhow.core.types import Field, FieldKind


def compile_registry(doctypes: list[type[DocType]]) -> Registry:
    """Compile a list of DocType classes into a Registry."""
    registry = Registry()
    for dt in doctypes:
        meta = dt.dhow_meta()
        entry = DocTypeEntry(
            name=meta["name"],
            fields={f["name"]: Field.from_dict(f) for f in meta["fields"]},
            workflow=meta["workflow"],
            controls=meta["controls"],
            permissions=meta["permissions"],
        )
        registry.add(entry)
    return registry


def diff_registry(old: Registry, new: Registry) -> dict[str, Any]:
    """Compute structural differences between two registries."""
    old_keys = set(old.doctypes.keys())
    new_keys = set(new.doctypes.keys())
    added = sorted(new_keys - old_keys)
    removed = sorted(old_keys - new_keys)
    changed: list[dict[str, Any]] = []
    for name in sorted(new_keys & old_keys):
        old_entry = old.doctypes[name].to_dict()
        new_entry = new.doctypes[name].to_dict()
        if old_entry != new_entry:
            changed.append({"name": name, "from": old_entry, "to": new_entry})
    return {"added": added, "removed": removed, "changed": changed}


class PydanticEmitter:
    """Emit Pydantic model source per DocType."""

    _PG_TO_PY: dict[FieldKind, str] = {
        FieldKind.TEXT: "str",
        FieldKind.INT: "int",
        FieldKind.DECIMAL: "Decimal",
        FieldKind.DATE: "date",
        FieldKind.DATETIME: "datetime",
        FieldKind.BOOL: "bool",
        FieldKind.JSON: "Any",
    }

    def emit(self, entry: DocTypeEntry) -> str:
        lines: list[str] = [
            "from datetime import date, datetime",
            "from decimal import Decimal",
            "from typing import Any, Optional",
            "from uuid import UUID",
            "",
            "from pydantic import BaseModel",
            "",
            f"class {entry.name}(BaseModel):",
        ]
        for field in entry.fields.values():
            py_type = self._field_type(field)
            default = " = None" if not field.required else ""
            lines.append(f"    {field.name}: {py_type}{default}")
        lines.append("")
        lines.append(f"class {entry.name}Response({entry.name}):")
        lines.append("    id: UUID")
        lines.append("    tenant_id: UUID")
        lines.append("    created_at: datetime")
        lines.append("    created_by: Optional[str] = None")
        lines.append("    updated_at: datetime")
        lines.append("    updated_by: Optional[str] = None")
        lines.append("")
        return "\n".join(lines) + "\n"

    def _field_type(self, field: Field) -> str:
        if field.kind in {FieldKind.LINK, FieldKind.SEQUENCE, FieldKind.TABLE}:
            return "str"
        if field.kind == FieldKind.STATE:
            states = field.options.get("states", [])
            return f"Literal{tuple(states)}" if states else "str"
        if field.kind == FieldKind.COMPUTED:
            return self._PG_TO_PY.get(field.options.get("returns", FieldKind.DECIMAL), "Any")
        return self._PG_TO_PY.get(field.kind, "Any")


class TypeScriptEmitter:
    """Emit TypeScript interfaces per DocType."""

    _PG_TO_TS: dict[FieldKind, str] = {
        FieldKind.TEXT: "string",
        FieldKind.INT: "number",
        FieldKind.DECIMAL: "number",
        FieldKind.DATE: "string",
        FieldKind.DATETIME: "string",
        FieldKind.BOOL: "boolean",
        FieldKind.JSON: "any",
    }

    def emit(self, entry: DocTypeEntry) -> str:
        lines: list[str] = [f"export interface {entry.name} {{"]
        for field in entry.fields.values():
            ts_type = self._field_type(field)
            optional = "" if field.required else "?"
            lines.append(f"  {field.name}{optional}: {ts_type};")
        lines.append("}")
        lines.append("")
        return "\n".join(lines) + "\n"

    def _field_type(self, field: Field) -> str:
        if field.kind in {FieldKind.LINK, FieldKind.SEQUENCE}:
            return "string"
        if field.kind == FieldKind.TABLE:
            return f"{field.options.get('child_doctype', 'Child')}[]"
        if field.kind == FieldKind.STATE:
            states = field.options.get("states", [])
            return " | ".join(f"'{s}'" for s in states) if states else "string"
        if field.kind == FieldKind.COMPUTED:
            return self._PG_TO_TS.get(field.options.get("returns", FieldKind.DECIMAL), "any")
        return self._PG_TO_TS.get(field.kind, "any")


class MCPEmitter:
    """Emit an MCP tool manifest JSON for all permitted operations."""

    _OPERATIONS = ["create", "read", "update", "delete", "submit"]

    def emit(self, registry: Registry) -> dict[str, Any]:
        tools: list[dict[str, Any]] = []
        for entry in registry.doctypes.values():
            grants = entry.permissions.get("grants", {})
            for op in self._OPERATIONS:
                roles = grants.get(op, {}).get("roles", [])
                if not roles:
                    continue
                tools.append(
                    {
                        "name": f"{entry.name.lower()}_{op}",
                        "description": f"{op.title()} a {entry.name} document",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string", "format": "uuid"},
                                "data": {"type": "object"},
                            },
                            "required": ["id"] if op in {"read", "update", "delete", "submit"} else [],
                        },
                        "roles": roles,
                    }
                )
        return {"tools": tools}


class AlembicEmitter:
    """Generate a minimal Alembic migration body from registry diff.

    Real migrations are explicit; this produces a skeleton that a human reviews.
    """

    def emit(self, diff: dict[str, Any]) -> str:
        lines = [
            '"""Dhow auto-generated migration."""',
            "",
            "from alembic import op",
            "import sqlalchemy as sa",
            "",
            "",
            "def upgrade() -> None:",
        ]
        for name in diff["added"]:
            lines.append(f"    # TODO: create table for {name}")
            lines.append(f"    op.create_table('{name.lower()}', sa.Column('id', sa.UUID(), primary_key=True))")
        for change in diff["changed"]:
            lines.append(f"    # TODO: alter table for {change['name']}")
        for name in diff["removed"]:
            lines.append(f"    op.drop_table('{name.lower()}')")
        if not (diff["added"] or diff["changed"] or diff["removed"]):
            lines.append("    pass")
        lines.extend(["", "", "def downgrade() -> None:", "    pass", ""])
        return "\n".join(lines)


def emit_all(
    registry: Registry,
    output_dir: Path,
    *,
    registry_path: Path | None = None,
) -> dict[str, Path]:
    """Emit registry JSON, Pydantic models, TypeScript types, MCP manifest, and audit DDL.

    The registry is written to `registry_path` (default: `output_dir/dhow_registry.json`).
    Derived artifacts are written under `output_dir`.
    """
    from dhow.engines.audit import audit_table_ddl, audit_trigger_function_sql

    output_dir.mkdir(parents=True, exist_ok=True)
    pydantic_dir = output_dir / "pydantic"
    ts_dir = output_dir / "typescript"
    mcp_dir = output_dir / "mcp"
    alembic_dir = output_dir / "alembic"
    sql_dir = output_dir / "sql"
    for d in (pydantic_dir, ts_dir, mcp_dir, alembic_dir, sql_dir):
        d.mkdir(parents=True, exist_ok=True)

    reg_path = registry_path or (output_dir / "dhow_registry.json")
    registry.save(reg_path)

    pydantic_emitter = PydanticEmitter()
    ts_emitter = TypeScriptEmitter()
    for entry in registry.doctypes.values():
        (pydantic_dir / f"{entry.name.lower()}.py").write_text(
            pydantic_emitter.emit(entry), encoding="utf-8"
        )
        (ts_dir / f"{entry.name.lower()}.ts").write_text(
            ts_emitter.emit(entry), encoding="utf-8"
        )

    mcp_path = mcp_dir / "tools.json"
    mcp_path.write_text(
        json.dumps(MCPEmitter().emit(registry), indent=2), encoding="utf-8"
    )

    # Placeholder Alembic skeleton (real migrations require diff against prior registry)
    empty_diff = {"added": list(registry.doctypes.keys()), "removed": [], "changed": []}
    alembic_path = alembic_dir / "initial_dhow_migration.py"
    alembic_path.write_text(AlembicEmitter().emit(empty_diff), encoding="utf-8")

    # Audit DDL: table + trigger function.
    (sql_dir / "audit.sql").write_text(
        f"{audit_table_ddl()}\n\n{audit_trigger_function_sql()}\n",
        encoding="utf-8",
    )

    return {
        "registry": reg_path,
        "pydantic": pydantic_dir,
        "typescript": ts_dir,
        "mcp": mcp_path,
        "alembic": alembic_path,
        "sql": sql_dir,
    }
