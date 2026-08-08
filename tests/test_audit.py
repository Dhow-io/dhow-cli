"""Tests for the audit engine helpers."""

from dhow import DocType, field
from dhow.core.compiler import compile_registry
from dhow.core.types import Operation
from dhow.engines.audit import (
    attach_audit_trigger_sql,
    audit_table_ddl,
    audit_trigger_function_sql,
    capture_record,
)
from dhow.engines.execute import engine
from dhow.engines.permissions import Actor


class Invoice(DocType):
    number = field.Sequence(prefix="INV-")
    total = field.Decimal(required=True)

    permissions = {"read": "all", "create": "clerk"}


async def test_capture_record_from_engine():
    registry = compile_registry([Invoice])
    eng = engine(registry)
    actor = Actor(user_id="u1", roles=("clerk",), tenant_id="t1")
    result = await eng.execute(Operation.CREATE, actor, "Invoice", data={"total": 100.00})
    assert result.ok

    record = capture_record("Invoice", Operation.CREATE, actor, None, result.data.get("fields"))
    assert record.doctype == "Invoice"
    assert record.operation == "create"
    assert record.actor_id == "u1"
    assert record.actor_role == "clerk"
    assert record.tenant_id == "t1"
    assert record.changed_fields == {"total": 100.0}


def test_audit_table_ddl_contains_append_only_policies():
    ddl = audit_table_ddl()
    assert "CREATE TABLE IF NOT EXISTS dhow_audit" in ddl
    assert "ALTER TABLE dhow_audit ENABLE ROW LEVEL SECURITY" in ddl
    assert "dhow_audit_append_only_update" in ddl
    assert "dhow_audit_append_only_delete" in ddl


def test_audit_trigger_function_sql():
    sql = audit_trigger_function_sql()
    assert "CREATE OR REPLACE FUNCTION dhow_audit_trigger()" in sql
    assert "INSERT INTO dhow_audit" in sql
    assert "TG_OP = 'DELETE'" in sql


def test_attach_audit_trigger_sql():
    sql = attach_audit_trigger_sql("invoice")
    assert "DROP TRIGGER IF EXISTS dhow_audit_invoice_trigger" in sql
    assert "CREATE TRIGGER dhow_audit_invoice_trigger" in sql
    assert "EXECUTE FUNCTION dhow_audit_trigger()" in sql
