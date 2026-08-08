# Permissions

Dhow uses a layered permission model. Every data operation is denied unless explicitly granted.

## Layers

1. **Role-based** — does the actor have a role allowed for this operation?
2. **Field-level** — is the actor allowed to read/write each field?
3. **Row-level** — does the row belong to the actor's tenant? Enforced by PostgreSQL RLS.

## Actor

```python
from dhow.engines.permissions import Actor

actor = Actor(
    user_id="u1",
    roles=("clerk", "manager"),
    tenant_id="t1",
)
```

`effective_role()` returns the most privileged role that initiated the request. When an agent is acting on behalf of a user, `agent_role` constrains the actor to that role.

## PermissionEngine

```python
from dhow.core.compiler import compile_registry
from dhow.engines.permissions import engine_for, Actor
from dhow.core.types import Operation

registry = compile_registry([Invoice])
perm = engine_for(registry)

actor = Actor(user_id="u1", roles=("clerk",), tenant_id="t1")
perm.check(actor, "Invoice", Operation.CREATE)  # raises PermissionError if denied
```

## Declarative grants

```python
class Invoice(DocType):
    total = field.Decimal(required=True)

    permissions = {
        "create": "clerk",
        "read": "all",
        "update": "clerk",
        "submit": "manager",
        "field_total": {"read": ["clerk", "manager"], "write": ["clerk"]},
    }
```

- `all` matches any authenticated actor.
- `[]` denies the operation for everyone.

## Field filtering

```python
from dhow.core.types import Operation

filtered = perm.filter_fields(
    actor, "Invoice", Operation.CREATE,
    {"total": 100.00, "secret": "x"}
)
# secret is dropped if the actor has no write grant
```

## Row-level security

Generated SQLAlchemy models bind `tenant_id` to `current_setting('app.tenant_id')::uuid` via a server default. RLS policies enforce tenant isolation at the database layer:

```sql
ALTER TABLE "public"."dt_invoice" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "public"."dt_invoice" FORCE ROW LEVEL SECURITY;
CREATE POLICY dt_invoice_tenant_isolation ON "public"."dt_invoice"
    USING (tenant_id = current_setting('app.tenant_id')::uuid);
```

Set the tenant in application code:

```python
from dhow.engines.persistence import set_tenant_sql

await session.execute(text(set_tenant_sql(str(tenant_id))))
```
