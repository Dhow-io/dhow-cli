# Testing

Dhow uses `pytest`. Run the full suite with:

```bash
python -m pytest -v
```

## Test categories

| File | What it tests |
|---|---|
| `tests/test_doctype.py` | DocType authoring, fields, workflows |
| `tests/test_compiler.py` | Registry compilation and emitters |
| `tests/test_permissions.py` | Role/field/row permission checks |
| `tests/test_persistence.py` | SQLAlchemy model generation and DDL |
| `tests/test_immutability.py` | Immutable-field triggers |
| `tests/test_api.py` | Generated FastAPI endpoints |
| `tests/test_cli.py` | CLI commands |
| `tests/test_audit.py` | Audit table DDL and capture |
| `tests/test_persistence_integration.py` | Live PostgreSQL integration |

## Running integration tests

The integration tests require a running Postgres server and the env var `DHOW_TEST_DATABASE_URL`:

```bash
# Using Homebrew PostgreSQL
brew services start postgresql@14

# Create role and database
psql -U $(whoami) -d postgres -c "CREATE ROLE dhow WITH LOGIN PASSWORD 'dhow';"
psql -U $(whoami) -d postgres -c "CREATE DATABASE dhow OWNER dhow;"

# Run integration tests
export DHOW_TEST_DATABASE_URL="postgresql+asyncpg://dhow:dhow@localhost:5432/dhow"
pytest tests/test_persistence_integration.py -v
```

Or use Docker Compose:

```bash
docker compose up -d postgres
export DHOW_TEST_DATABASE_URL="postgresql+asyncpg://dhow:dhow@localhost:5432/dhow"
pytest tests/test_persistence_integration.py -v
```

## Test output

Recent run:

```text
50 passed, 1 skipped, 1 warning
```

The skipped test is `test_rls_blocks_cross_tenant_read`, which only runs when `DHOW_TEST_DATABASE_URL` is set.
