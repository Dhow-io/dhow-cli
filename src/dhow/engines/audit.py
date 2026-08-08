"""Audit helpers: in-memory audit log and audit-table SQL generation."""

from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from typing import Any

from dhow.core.types import Operation
from dhow.engines.permissions import Actor


@dataclass
class AuditRecord:
    """A single audit record captured during engine.execute()."""

    timestamp: str
    doctype: str
    operation: str
    doc_id: str | None
    actor_id: str | None
    actor_role: str | None
    tenant_id: str | None
    changed_fields: dict[str, Any] = dc_field(default_factory=dict)


def capture_record(
    doctype: str,
    operation: Operation,
    actor: Actor,
    doc_id: str | None,
    changed_fields: dict[str, Any] | None = None,
) -> AuditRecord:
    """Build an audit record from an executed operation."""
    return AuditRecord(
        timestamp=datetime.now(timezone.utc).isoformat(),
        doctype=doctype,
        operation=operation.value,
        doc_id=doc_id,
        actor_id=actor.user_id,
        actor_role=actor.effective_role(),
        tenant_id=actor.tenant_id,
        changed_fields=changed_fields or {},
    )


def audit_table_ddl() -> str:
    """DDL for the central append-only dhow_audit table."""
    return """
CREATE TABLE IF NOT EXISTS dhow_audit (
    id BIGSERIAL PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    doctype TEXT NOT NULL,
    operation TEXT NOT NULL,
    doc_id TEXT,
    actor_id TEXT,
    actor_role TEXT,
    tenant_id TEXT,
    changed_fields JSONB,
    tenant_isolation TEXT GENERATED ALWAYS AS (coalesce(tenant_id::text, '')) STORED
);

CREATE INDEX IF NOT EXISTS idx_dhow_audit_doctype ON dhow_audit(doctype);
CREATE INDEX IF NOT EXISTS idx_dhow_audit_doc_id ON dhow_audit(doc_id);
CREATE INDEX IF NOT EXISTS idx_dhow_audit_tenant ON dhow_audit(tenant_isolation);

-- Audit rows are append-only: deny UPDATE and DELETE to everyone.
ALTER TABLE dhow_audit ENABLE ROW LEVEL SECURITY;
CREATE POLICY dhow_audit_append_only_update ON dhow_audit AS RESTRICTIVE FOR UPDATE USING (false);
CREATE POLICY dhow_audit_append_only_delete ON dhow_audit AS RESTRICTIVE FOR DELETE USING (false);
""".strip()


def audit_trigger_function_sql() -> str:
    """PL/pgSQL function that writes an audit row on data changes."""
    return """
CREATE OR REPLACE FUNCTION dhow_audit_trigger()
RETURNS TRIGGER AS $$
DECLARE
    changed JSONB := '{}'::JSONB;
    rec_id TEXT;
BEGIN
    IF TG_OP = 'DELETE' THEN
        rec_id := OLD.id::TEXT;
        changed := to_jsonb(OLD);
        INSERT INTO dhow_audit (doctype, operation, doc_id, actor_id, actor_role, tenant_id, changed_fields)
        VALUES (TG_TABLE_NAME, 'delete', rec_id, current_setting('dhow.actor_id', true), current_setting('dhow.actor_role', true), current_setting('dhow.tenant_id', true), changed);
        RETURN OLD;
    ELSIF TG_OP = 'UPDATE' THEN
        rec_id := NEW.id::TEXT;
        changed := jsonb_strip_nulls(to_jsonb(NEW));
        INSERT INTO dhow_audit (doctype, operation, doc_id, actor_id, actor_role, tenant_id, changed_fields)
        VALUES (TG_TABLE_NAME, 'update', rec_id, current_setting('dhow.actor_id', true), current_setting('dhow.actor_role', true), current_setting('dhow.tenant_id', true), changed);
        RETURN NEW;
    ELSE
        rec_id := NEW.id::TEXT;
        changed := jsonb_strip_nulls(to_jsonb(NEW));
        INSERT INTO dhow_audit (doctype, operation, doc_id, actor_id, actor_role, tenant_id, changed_fields)
        VALUES (TG_TABLE_NAME, 'create', rec_id, current_setting('dhow.actor_id', true), current_setting('dhow.actor_role', true), current_setting('dhow.tenant_id', true), changed);
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;
""".strip()


def attach_audit_trigger_sql(table_name: str) -> str:
    """Attach the audit trigger to a given table."""
    trigger_name = f"dhow_audit_{table_name}_trigger"
    return f"""
DROP TRIGGER IF EXISTS {trigger_name} ON {table_name};
CREATE TRIGGER {trigger_name}
AFTER INSERT OR UPDATE OR DELETE ON {table_name}
FOR EACH ROW
EXECUTE FUNCTION dhow_audit_trigger();
""".strip()
