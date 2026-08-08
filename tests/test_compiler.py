"""Tests for the metadata compiler."""

from pathlib import Path

import pytest

from dhow import DocType, field
from dhow.core.compiler import (
    AlembicEmitter,
    MCPEmitter,
    PydanticEmitter,
    TypeScriptEmitter,
    compile_registry,
    diff_registry,
    emit_all,
)
from dhow.core.registry import Registry


class Customer(DocType):
    name = field.Text(required=True)


class Invoice(DocType):
    number = field.Sequence(prefix="INV-", immutable=True)
    customer = field.Link("Customer", required=True, index=True)
    total = field.Computed("sum(lines.amount)", store=True, index=True)

    permissions = {"read": "all", "create": "clerk", "submit": "manager"}


def test_compile_registry_captures_meta():
    registry = compile_registry([Customer, Invoice])
    assert set(registry.doctypes.keys()) == {"Customer", "Invoice"}
    inv = registry.doctypes["Invoice"]
    assert inv.fields["number"].kind.value == "sequence"
    assert inv.fields["customer"].options["target_doctype"] == "Customer"


def test_diff_registry_detects_additions():
    old = compile_registry([Customer])
    new = compile_registry([Customer, Invoice])
    diff = diff_registry(old, new)
    assert diff["added"] == ["Invoice"]
    assert diff["removed"] == []
    assert diff["changed"] == []


def test_diff_registry_detects_changes():
    old = compile_registry([Customer])
    # Build a second registry where the same logical DocType gains a field.
    changed = compile_registry([Customer])
    changed.doctypes["Customer"].fields["email"] = field.Text().with_name("email")
    diff = diff_registry(old, changed)
    assert diff["changed"][0]["name"] == "Customer"


def test_pydantic_emitter():
    registry = compile_registry([Invoice])
    src = PydanticEmitter().emit(registry.doctypes["Invoice"])
    assert "class Invoice(BaseModel):" in src
    assert "number: str" in src


def test_typescript_emitter():
    registry = compile_registry([Invoice])
    src = TypeScriptEmitter().emit(registry.doctypes["Invoice"])
    assert "export interface Invoice {" in src


def test_mcp_emitter():
    registry = compile_registry([Invoice])
    manifest = MCPEmitter().emit(registry)
    names = {t["name"] for t in manifest["tools"]}
    assert "invoice_create" in names
    assert "invoice_submit" in names


def test_alembic_emitter():
    diff = {"added": ["Invoice"], "removed": [], "changed": []}
    src = AlembicEmitter().emit(diff)
    assert "def upgrade()" in src
    assert "create_table('invoice'" in src


def test_emit_all_creates_files(tmp_path: Path):
    registry = compile_registry([Customer, Invoice])
    paths = emit_all(registry, tmp_path)
    assert paths["registry"].exists()
    assert (paths["pydantic"] / "customer.py").exists()
    assert (paths["typescript"] / "invoice.ts").exists()
    assert paths["mcp"].exists()
    assert paths["alembic"].exists()

    saved = Registry.load(paths["registry"])
    assert "Invoice" in saved.doctypes
