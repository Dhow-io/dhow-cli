"""Per-(doctype, tenant) PostgreSQL sequence helpers."""

from __future__ import annotations


def sequence_name(doctype: str, field: str, tenant_id: str) -> str:
    """Return a stable sequence name for a DocType + field + tenant."""
    safe_tenant = tenant_id.replace("-", "_")
    return f"seq_dt_{doctype.lower()}_{field.lower()}_{safe_tenant}"


def create_sequence_sql(name: str, prefix: str = "") -> str:
    """DDL to create a sequence with optional prefix handled by default value."""
    return f"CREATE SEQUENCE IF NOT EXISTS {name};"


def next_value_sql(name: str, prefix: str = "") -> str:
    """Return SQL expression for the next formatted sequence value."""
    if prefix:
        return f"'{prefix}' || nextval('{name}'::regclass)"
    return f"nextval('{name}'::regclass)"
