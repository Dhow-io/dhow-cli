"""Tests for immutability trigger DDL generation."""

from dhow import DocType, field
from dhow.core.compiler import compile_registry
from dhow.engines.immutability import immutability_ddl, immutable_after_trigger_sql, immutable_field_trigger_sql


class Invoice(DocType):
    number = field.Sequence(prefix="INV-", immutable=True)
    status = field.State(["draft", "submitted"])

    controls = []


def test_immutable_field_trigger():
    sql = immutable_field_trigger_sql("dt_invoice", ["number"])
    assert "RAISE EXCEPTION 'Field number is immutable on dt_invoice'" in sql
    assert "BEFORE UPDATE OR DELETE" in sql


def test_immutable_after_trigger():
    sql = immutable_after_trigger_sql("dt_invoice", "status", ["submitted"])
    assert "OLD.status IN ('submitted')" in sql
    assert "RAISE EXCEPTION 'Record is locked" in sql


def test_immutability_ddl_from_entry():
    registry = compile_registry([Invoice])
    entry = registry.doctypes["Invoice"].to_dict()
    ddl = immutability_ddl(entry, "dt_invoice")
    assert len(ddl) == 1
    assert "Field number is immutable" in ddl[0]
