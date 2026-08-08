# REST API

Dhow generates a FastAPI application from the compiled registry. Every endpoint routes through `engine.execute()`, so permissions are enforced on every request.

## Generated endpoints

For each DocType `Invoice`, the generator creates:

- `GET /invoice` — list invoices (`read`)
- `GET /invoice/{id}` — get one invoice (`read`)
- `POST /invoice` — create an invoice (`create`)
- `PUT /invoice/{id}` — update an invoice (`update`)
- `DELETE /invoice/{id}` — delete an invoice (`delete`)
- `POST /invoice/{id}/submit` — submit transition (`submit`)

## Authentication

Roles are passed via the `X-Roles` header. In production this should be replaced by a real authentication dependency.

```bash
curl -H "X-Roles: clerk" http://localhost:8000/invoice
```

## Request/response models

Pydantic request and response models are generated per DocType and registered with FastAPI. They include:

- all declared fields
- standard columns: `id`, `tenant_id`, `created_at`, `created_by`, `updated_at`, `updated_by`

## Permission mapping

| HTTP | Operation | Grant required |
|---|---|---|
| `POST` | `create` | `permissions["create"]` |
| `GET` | `read` | `permissions["read"]` |
| `PUT` | `update` | `permissions["update"]` |
| `DELETE` | `delete` | `permissions["delete"]` |
| `POST /{id}/submit` | `submit` | `permissions["submit"]` |

A missing role returns `403 Forbidden`.

## Example

```bash
# create as clerk
curl -X POST http://localhost:8000/invoice \
  -H "Content-Type: application/json" \
  -H "X-Roles: clerk" \
  -d '{"total": 100.00}'

# submit as manager
curl -X POST http://localhost:8000/invoice/123e4567-e89b-12d3-a456-426614174000/submit \
  -H "X-Roles: manager"
```

## Running the server

```bash
dhow serve
```

Interactive docs: `http://localhost:8000/docs`.

## Customizing the app

Edit `src/dhow/generated/app.py` or supply a custom module to `uvicorn`:

```bash
uvicorn myapp.api:app --reload
```
