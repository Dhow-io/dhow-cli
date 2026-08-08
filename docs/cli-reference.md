# CLI Reference

Dhow provides a Typer-based CLI. Every command supports `--json` for machine-readable output.

## Global options

- `--json` — emit JSON instead of human-readable text (where supported).
- `--help` — show command help.

## `dhow init`

Scaffold a new Dhow project.

```bash
dhow init myapp
```

Creates:

```
myapp/
  pyproject.toml
  dhow.toml
  modules/
```

## `dhow new module <name>`

Create a new module directory.

```bash
dhow new module sales
```

## `dhow new doctype <module> <name>`

Create a new DocType file under a module.

```bash
dhow new doctype sales Invoice
```

File: `modules/sales/doctypes/invoice.py`.

## `dhow build`

Compile all DocTypes and emit artifacts.

```bash
dhow build
```

Output:

```
dist/
  registry.json
  pydantic/
  typescript/
  mcp/tools.json
  alembic/
  sql/
```

## `dhow diff`

Show pending changes between the current DocType source and the last built registry.

```bash
dhow diff
```

Example output:

```text
added:
  - Invoice
changed: []
removed: []
```

## `dhow describe <doctype>`

Describe a DocType from the compiled registry.

```bash
dhow describe Invoice
```

## `dhow schema-search <term>`

Search compiled Pydantic schemas and TypeScript types for a term.

```bash
dhow schema-search invoice
```

## `dhow serve`

Run the generated FastAPI application.

```bash
dhow serve --host 0.0.0.0 --port 8000
```

Options:

- `--host` (default `127.0.0.1`)
- `--port` (default `8000`)
- `--reload` (default `False`)

## `dhow doctor`

Check project health.

```bash
dhow doctor
```

Checks registry compilation, artifact presence, and database connectivity if a URL is configured.

## `dhow migrate`

Apply or roll back database migrations. Currently a placeholder.

## `dhow seed`

Seed the database with demo data. Currently a placeholder.

## `dhow test`

Run project tests via `pytest`.

```bash
dhow test
```
