"""Project scaffolding logic for `dhow init`."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def scaffold_project(name: str, target: Path) -> Path:
    """Create a minimal Dhow project skeleton at `target`."""
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"Target directory is not empty: {target}")

    directories = [
        "modules",
        "modules/doctypes",
        "migrations",
        "schemas/pydantic",
        "schemas/typescript",
        "mcp",
        "tests",
    ]
    for directory in directories:
        (target / directory).mkdir(parents=True, exist_ok=True)

    _write_file(target / "dhow.toml", _dhow_toml(name))
    _write_file(target / "modules" / "__init__.py", "")
    _write_file(target / "modules" / "doctypes" / "__init__.py", "")
    _write_file(
        target / "modules" / "doctypes" / "invoice.py",
        _invoice_doctype_template(),
    )
    _write_file(
        target / "modules" / "doctypes" / "invoice_line.py",
        _invoice_line_doctype_template(),
    )
    _write_file(target / "tests" / "__init__.py", "")
    _write_file(
        target / "tests" / "test_invoice.py",
        _invoice_test_template(),
    )
    _write_file(
        target / ".env.example",
        _env_example(),
    )

    return target


def _write_file(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _dhow_toml(name: str) -> str:
    return f"""[project]
name = "{name}"
version = "0.1.0"
database_url = "postgresql+asyncpg://dhow:dhow@localhost:5432/dhow"
redis_url = "redis://localhost:6379/0"

[build]
registry_path = "migrations/dhow_registry.json"
migrations_dir = "migrations/alembic"
pydantic_dir = "schemas/pydantic"
typescript_dir = "schemas/typescript"
mcp_manifest = "mcp/tools.json"

[permissions]
default_roles = ["admin", "manager", "clerk", "guest"]
"""


def _invoice_doctype_template() -> str:
    return '''from dhow import DocType, field


class Invoice(DocType):
    number = field.Sequence(prefix="INV-", immutable=True)
    customer = field.Link("Customer", required=True, index=True)
    date = field.Date(default="today", required=True)
    lines = field.Table("InvoiceLine", required=True)
    status = field.State(["draft", "submitted", "paid", "cancelled"])
    total = field.Computed("sum(lines.amount)", store=True, index=True)

    workflow = None
    controls = []
    permissions = {
        "read": "all",
        "create": "clerk",
        "update": "clerk",
        "submit": "manager",
    }
'''


def _invoice_line_doctype_template() -> str:
    return '''from dhow import DocType, field


class InvoiceLine(DocType):
    invoice = field.Link("Invoice", required=True, index=True)
    item = field.Text(required=True)
    quantity = field.Int(required=True)
    rate = field.Decimal(required=True)
    amount = field.Computed("quantity * rate", store=True)
'''


def _invoice_test_template() -> str:
    return '''from modules.doctypes.invoice import Invoice


def test_invoice_has_fields():
    meta = Invoice.dhow_meta()
    names = {f["name"] for f in meta["fields"]}
    assert names >= {"number", "customer", "date", "lines", "status", "total"}
'''


def _env_example() -> str:
    return """DHOW_DATABASE_URL=postgresql+asyncpg://dhow:dhow@localhost:5432/dhow
DHOW_REDIS_URL=redis://localhost:6379/0
DHOW_TENANT_ID=default
"""
