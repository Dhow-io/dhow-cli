# DocType Authoring

A `DocType` is a Python class that describes a business entity: its fields, permissions, workflow, and data controls.

## Minimal example

```python
from dhow import DocType, field

class Customer(DocType):
    name = field.Text(required=True)
    email = field.Text(unique=True)
```

## Fields

Use the `field` factory:

| Kind | Example | Stored as |
|---|---|---|
| Text | `field.Text()` | `TEXT` |
| Int | `field.Int()` | `INTEGER` |
| Decimal | `field.Decimal()` | `NUMERIC(18,4)` |
| Date | `field.Date()` | `DATE` |
| DateTime | `field.DateTime()` | `TIMESTAMP WITH TIME ZONE` |
| Bool | `field.Bool()` | `BOOLEAN` |
| Link | `field.Link("Customer", required=True)` | `VARCHAR(255)` |
| State | `field.State(states=["Draft", "Submitted"])` | `VARCHAR(255)` |
| Sequence | `field.Sequence(prefix="INV-")` | `VARCHAR(255)` |
| JSON | `field.JSON()` | `TEXT` (serialized) |
| Computed | `field.Computed(returns=FieldKind.DECIMAL)` | `NUMERIC(18,4)` |
| Table | `field.Table("InvoiceItem")` | child table |

Common options:

- `required=True` — not-null column.
- `unique=True` — unique constraint.
- `index=True` — database index.
- `immutable=True` — value cannot change after create (via trigger).
- `hidden=True` — omitted from read responses for roles without field grants.
- `read_only=True` — forbidden in create/update payloads.
- `label="Display Name"` — human-readable label.

## Permissions

Declare `permissions` as a class attribute:

```python
class Invoice(DocType):
    number = field.Sequence(prefix="INV-")
    total = field.Decimal(required=True)

    permissions = {
        "create": "clerk",
        "read": "all",
        "update": "clerk",
        "submit": "manager",
        "delete": [],
        "field_total": {"read": ["clerk", "manager"], "write": ["clerk"]},
    }
```

- Operation keys: `create`, `read`, `update`, `delete`, `submit`.
- `all` allows any authenticated actor.
- `[]` explicitly denies.
- `field_<name>` entries are field-level grants.

## Workflows

### State machine

```python
from dhow.core.workflow import StateMachine

class Invoice(DocType):
    status = field.State(states=["Draft", "Submitted", "Paid"], default="Draft")
    workflow = StateMachine(
        field="status",
        transitions={
            "Draft": ["Submitted"],
            "Submitted": ["Paid", "Cancelled"],
        },
    )
```

### Approval

```python
from dhow.core.workflow import Approval

class Invoice(DocType):
    approved = field.Bool(default=False)
    workflow = Approval(field="approved", approver_role="manager")
```

## Controls

```python
from dhow.core.controls import ImmutableAfter

class Invoice(DocType):
    number = field.Sequence(prefix="INV-")
    controls = ImmutableAfter(field="number")
```

`ImmutableAfter` emits a PostgreSQL trigger that rejects updates to the field after the row is created.

## Compile and inspect

```python
from dhow.core.compiler import compile_registry
from dhow import DocType, field

class Customer(DocType):
    name = field.Text(required=True)

registry = compile_registry([Customer])
print(registry.to_dict())
```
