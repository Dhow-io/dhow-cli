"""Persistence engine: generate SQLAlchemy models from the registry."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    UUID,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from dhow.core.registry import DocTypeEntry, Registry
from dhow.core.types import Field, FieldKind


class Base(DeclarativeBase):
    """SQLAlchemy declarative base for Dhow-generated models."""

    metadata = MetaData(schema="public")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _standard_columns() -> list[Any]:
    """Columns present on every Dhow table."""
    return [
        mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        mapped_column(UUID(as_uuid=True), nullable=False),
        mapped_column(DateTime(timezone=True), nullable=False, default=_now),
        mapped_column(String(255), nullable=True),
        mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now),
        mapped_column(String(255), nullable=True),
    ]


def _field_to_column(field: Field) -> Any:
    """Map a Dhow Field to a SQLAlchemy column definition."""
    kwargs: dict[str, Any] = {"nullable": not field.required}
    if field.unique:
        kwargs["unique"] = True

    if field.kind == FieldKind.TEXT:
        return mapped_column(Text, **kwargs)
    if field.kind == FieldKind.INT:
        return mapped_column(Integer, **kwargs)
    if field.kind == FieldKind.DECIMAL:
        return mapped_column(Numeric(18, 4), **kwargs)
    if field.kind == FieldKind.DATE:
        return mapped_column(Date, **kwargs)
    if field.kind == FieldKind.DATETIME:
        return mapped_column(DateTime(timezone=True), **kwargs)
    if field.kind == FieldKind.BOOL:
        return mapped_column(Boolean, **kwargs)
    if field.kind in {FieldKind.LINK, FieldKind.SEQUENCE, FieldKind.STATE}:
        return mapped_column(String(255), **kwargs)
    if field.kind == FieldKind.JSON:
        return mapped_column(Text, **kwargs)
    if field.kind == FieldKind.COMPUTED:
        # Stored computed columns are decimals by default; expr evaluated in trigger/app.
        return mapped_column(Numeric(18, 4), **kwargs)
    if field.kind == FieldKind.TABLE:
        # Child tables declare their own FK; omit here.
        return None
    return mapped_column(Text, **kwargs)


def _create_table_name(doctype_name: str) -> str:
    return f"dt_{doctype_name.lower()}"


def _create_child_table_name(parent: str, field: Field) -> str:
    child = field.options.get("child_doctype", f"{parent}_child").lower()
    return f"dt_{child}"


def model_class_from_entry(entry: DocTypeEntry, base: type[DeclarativeBase] = Base) -> type[Any]:
    """Build a SQLAlchemy declarative class from a registry entry."""
    table_name = _create_table_name(entry.name)
    schema = getattr(base.metadata, "schema", "public")
    attrs: dict[str, Any] = {
        "__tablename__": table_name,
        "__table_args__": {"schema": schema},
        "id": mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        "tenant_id": mapped_column(
            UUID(as_uuid=True),
            nullable=False,
            server_default=text("current_setting('app.tenant_id')::uuid"),
        ),
        "created_at": mapped_column(DateTime(timezone=True), nullable=False, default=_now),
        "created_by": mapped_column(String(255), nullable=True),
        "updated_at": mapped_column(DateTime(timezone=True), nullable=False, default=_now, onupdate=_now),
        "updated_by": mapped_column(String(255), nullable=True),
    }

    for field in entry.fields.values():
        if field.kind == FieldKind.TABLE:
            continue
        col = _field_to_column(field)
        if col is not None:
            attrs[field.name] = col
        if field.index:
            attrs[f"idx_{field.name}"] = Index(f"idx_{table_name}_{field.name}", field.name)

    return type(entry.name, (base,), attrs)


def build_models(registry: Registry, metadata: MetaData | None = None) -> dict[str, type[Any]]:
    """Generate SQLAlchemy model classes for all DocTypes in the registry.

    Uses a fresh declarative base bound to the supplied metadata (or fresh public-schema
    metadata) so repeated calls do not collide with an existing Base.metadata.
    """
    if metadata is None:
        metadata = MetaData(schema="public")

    GeneratedBase = type("GeneratedBase", (DeclarativeBase,), {"metadata": metadata})

    return {name: model_class_from_entry(entry, base=GeneratedBase) for name, entry in registry.doctypes.items()}


def rls_policy_sql(table_name: str, schema: str = "public") -> list[str]:
    """Return the RLS policy DDL statements for a Dhow table."""
    full_name = f'"{schema}"."{table_name}"'
    return [
        f"ALTER TABLE {full_name} ENABLE ROW LEVEL SECURITY;",
        f"ALTER TABLE {full_name} FORCE ROW LEVEL SECURITY;",
        f"CREATE POLICY {table_name}_tenant_isolation ON {full_name}"
        " USING (tenant_id = current_setting('app.tenant_id')::uuid);",
    ]


def set_tenant_sql(tenant_id: str) -> str:
    return f"SELECT set_config('app.tenant_id', '{tenant_id}', false);"


def audit_trigger_sql(audit_table: str = "dhow_audit", schema: str = "public") -> str:
    """Trigger function that writes every mutation to the append-only audit table."""
    return f"""
CREATE OR REPLACE FUNCTION {schema}.dhow_audit_trigger()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        INSERT INTO {schema}.{audit_table} (id, tenant_id, doctype, doc_id, action, old_data, new_data, actor, source, created_at)
        VALUES (gen_random_uuid(), OLD.tenant_id, TG_TABLE_NAME, OLD.id, 'DELETE', row_to_json(OLD), NULL, current_setting('app.user_id', true), current_setting('app.source', true), now());
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' THEN
        INSERT INTO {schema}.{audit_table} (id, tenant_id, doctype, doc_id, action, old_data, new_data, actor, source, created_at)
        VALUES (gen_random_uuid(), NEW.tenant_id, TG_TABLE_NAME, NEW.id, 'UPDATE', row_to_json(OLD), row_to_json(NEW), current_setting('app.user_id', true), current_setting('app.source', true), now());
        RETURN NEW;
    ELSIF TG_OP = 'INSERT' THEN
        INSERT INTO {schema}.{audit_table} (id, tenant_id, doctype, doc_id, action, old_data, new_data, actor, source, created_at)
        VALUES (gen_random_uuid(), NEW.tenant_id, TG_TABLE_NAME, NEW.id, 'CREATE', NULL, row_to_json(NEW), current_setting('app.user_id', true), current_setting('app.source', true), now());
        RETURN NEW;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
""".strip()


def attach_audit_trigger_sql(table_name: str, schema: str = "public") -> str:
    return f"""
DROP TRIGGER IF EXISTS {table_name}_audit ON {schema}.{table_name};
CREATE TRIGGER {table_name}_audit
AFTER INSERT OR UPDATE OR DELETE ON {schema}.{table_name}
FOR EACH ROW EXECUTE FUNCTION {schema}.dhow_audit_trigger();
""".strip()
