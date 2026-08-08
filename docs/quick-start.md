# Quick Start

Install Dhow from PyPI and scaffold your first project.

## Install

```bash
pip install dhow
```

Or clone the repo and install in editable mode:

```bash
git clone https://github.com/Dhow-io/dhow-cli.git
cd dhow-cli
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Create a project

```bash
dhow init myapp
cd myapp
```

This creates a minimal Dhow project with a `pyproject.toml`, `dhow.toml`, and a `modules/` directory.

## Define a DocType

```bash
dhow new module sales
dhow new doctype sales Invoice
```

Edit `modules/sales/doctypes/invoice.py`:

```python
from dhow import DocType, field

class Invoice(DocType):
    number = field.Sequence(prefix="INV-")
    customer = field.Link("Customer", required=True)
    total = field.Decimal(required=True)
    status = field.State(states=["Draft", "Submitted", "Paid"], default="Draft")

    permissions = {
        "create": "clerk",
        "read": "all",
        "submit": "manager",
    }
```

## Build metadata artifacts

```bash
dhow build
```

This emits:

- `dist/registry.json` — canonical registry
- `dist/pydantic/` — Pydantic request/response models
- `dist/typescript/` — TypeScript interfaces
- `dist/mcp/tools.json` — MCP tool manifest
- `dist/alembic/` — placeholder migration skeleton
- `dist/sql/` — audit DDL and RLS policies

## Run the API

```bash
dhow serve
```

The generated FastAPI app is available at `http://localhost:8000`. Open `http://localhost:8000/docs` for interactive Swagger UI.

## Test permissions

```bash
curl -X POST http://localhost:8000/invoice \
  -H "Content-Type: application/json" \
  -H "X-Roles: clerk" \
  -d '{"total": 100.00}'
```

A request without the `clerk` role receives `403 Forbidden`.

## Next steps

- Read [DocType Authoring](doctype-authoring.md) for fields, workflows, and controls.
- Read [CLI Reference](cli-reference.md) for all commands.
- Read [REST API](rest-api.md) for endpoint details.
