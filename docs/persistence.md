# Persistence

Dhow generates SQLAlchemy models from the registry and emits PostgreSQL-specific DDL for tenant isolation, sequences, immutability, and audit logging.

## Building models

```python
from dhow.core.compiler import compile_registry
from dhow.engines.persistence import build_models

registry = compile_registry([Customer, Invoice])
models = build_models(registry)

CustomerModel = models["Customer"]
InvoiceModel = models["Invoice"]
```

`build_models()` creates a fresh declarative base and `MetaData` so repeated calls do not collide.

## Standard columns

Every generated table has:

- `id` — UUID primary key
- `tenant_id` — UUID, not null, server default from `current_setting('app.tenant_id')::uuid`
- `created_at`, `created_by`, `updated_at`, `updated_by` — audit stamps

## Row-level security

Generate RLS DDL with `rls_policy_sql()`:

```python
from dhow.engines.persistence import rls_policy_sql

for statement in rls_policy_sql("dt_invoice"):
    await conn.execute(text(statement))
```

RLS is forced even for the table owner.

## Sequences

Sequence fields are backed by per-tenant PostgreSQL sequences:

```python
from dhow.engines.sequences import sequence_name, create_sequence_sql

seq = sequence_name("Invoice", "number", str(tenant_id))
await conn.execute(text(create_sequence_sql(seq)))
result = await conn.execute(text(f"SELECT nextval('{seq}')"))
number = f"INV-{result.scalar()}"
```

## Immutability triggers

`ImmutableAfter` controls emit triggers that reject updates to protected fields:

```python
from dhow.engines.immutability import immutable_field_trigger_sql

sql = immutable_field_trigger_sql("dt_invoice", "number")
await conn.execute(text(sql))
```

## Audit table

`dhow.engines.audit` generates DDL for an append-only `dhow_audit` table and a trigger function that records every change:

```python
from dhow.engines.audit import (
    audit_table_ddl,
    audit_trigger_function_sql,
    attach_audit_trigger_sql,
)

await conn.execute(text(audit_table_ddl()))
await conn.execute(text(audit_trigger_function_sql()))
await conn.execute(text(attach_audit_trigger_sql("dt_invoice")))
```

The audit table is protected by RLS policies that deny `UPDATE` and `DELETE`.

## docker-compose

A Postgres service is included in `docker-compose.yml`:

```bash
docker compose up -d postgres
```

Default connection: `postgresql+asyncpg://dhow:dhow@localhost:5432/dhow`.
