# Screenshots

This folder is intended for PNG screenshots of the Dhow CLI and generated FastAPI Swagger UI.

The live screenshots below were captured as text artifacts during the documentation pass. Convert them to PNG by running the commands in a terminal or browser and saving the result.

## CLI help

Run:

```bash
dhow --help
```

See [`cli-help.md`](../cli-help.md) for the captured text.

## Project build output

Run inside a Dhow project:

```bash
dhow build
```

See [`../demo-build.md`](../demo-build.md) for captured output.

## Swagger UI

Run inside a Dhow project:

```bash
dhow serve
```

Then open `http://127.0.0.1:8000/docs` in a browser. The generated docs show:

- `GET /invoice` — list invoices
- `POST /invoice` — create invoice
- `POST /invoice/{id}/submit` — submit transition

Use the `Authorize` button (or `X-Roles` header) to test permission-gated endpoints.

## Permission denied example

```bash
curl -X POST http://127.0.0.1:8000/invoice \
  -H "Content-Type: application/json" \
  -H "X-Roles: guest" \
  -d '{"customer":"cust-001","date":"2026-08-08","status":"draft","total":100}'
```

Response:

```json
{"detail":"guest cannot create Invoice"}
```
