"""Immutability controls enforced via BEFORE UPDATE/DELETE triggers."""

from __future__ import annotations

from typing import Any


def immutable_field_trigger_sql(table_name: str, fields: list[str], schema: str = "public") -> str:
    """Trigger function that blocks UPDATE/DELETE on immutable fields."""
    checks = []
    for field in fields:
        checks.append(
            f"IF NEW.{field} IS DISTINCT FROM OLD.{field} THEN\n"
            f"        RAISE EXCEPTION 'Field {field} is immutable on {table_name}';\n"
            "    END IF;"
        )
    body = "\n    ".join(checks)
    return f"""
CREATE OR REPLACE FUNCTION {schema}.trg_{table_name}_immutable_fields()
RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'Table {table_name} is append-only / immutable';
    END IF;
    {body}
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS {table_name}_immutable_fields ON {schema}.{table_name};
CREATE TRIGGER {table_name}_immutable_fields
BEFORE UPDATE OR DELETE ON {schema}.{table_name}
FOR EACH ROW EXECUTE FUNCTION {schema}.trg_{table_name}_immutable_fields();
""".strip()


def immutable_after_trigger_sql(
    table_name: str,
    state_field: str,
    values: list[str],
    schema: str = "public",
) -> str:
    """Trigger that blocks mutation once a state field reaches one of the listed values."""
    value_list = ", ".join(f"'{v}'" for v in values)
    return f"""
CREATE OR REPLACE FUNCTION {schema}.trg_{table_name}_immutable_after()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.{state_field} IN ({value_list}) THEN
        RAISE EXCEPTION 'Record is locked because {state_field} is in ({value_list})';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS {table_name}_immutable_after ON {schema}.{table_name};
CREATE TRIGGER {table_name}_immutable_after
BEFORE UPDATE OR DELETE ON {schema}.{table_name}
FOR EACH ROW EXECUTE FUNCTION {schema}.trg_{table_name}_immutable_after();
""".strip()


def immutability_ddl(entry: dict[str, Any], table_name: str, schema: str = "public") -> list[str]:
    """Collect all immutability DDL for a registry entry."""
    statements: list[str] = []
    immutable_fields = [
        f["name"]
        for f in entry.get("fields", [])
        if f.get("immutable") and f["kind"] not in {"computed", "table"}
    ]
    if immutable_fields:
        statements.append(immutable_field_trigger_sql(table_name, immutable_fields, schema))

    for control in entry.get("controls", []):
        if control.get("kind") == "immutable_after":
            statements.append(
                immutable_after_trigger_sql(
                    table_name,
                    control["state_field"],
                    control.get("values", []),
                    schema,
                )
            )
    return statements
