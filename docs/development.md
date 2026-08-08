# Development

Contribute to Dhow or extend it for your own project.

## Project layout

```text
dhow-cli/
  src/dhow/
    cli/          # Typer commands
    core/         # DocType API, compiler, registry
    engines/      # permissions, persistence, audit, sequences, immutability
    generators/   # FastAPI app generator
    generated/    # runtime app module
  tests/          # pytest suite
  docs/           # this documentation
  docker-compose.yml
  pyproject.toml
```

## Setup

```bash
git clone https://github.com/Dhow-io/dhow-cli.git
cd dhow-cli
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running tests

```bash
python -m pytest -v
```

With live Postgres integration:

```bash
export DHOW_TEST_DATABASE_URL="postgresql+asyncpg://dhow:dhow@localhost:5432/dhow"
python -m pytest -v
```

## Adding a field kind

1. Add a new `FieldKind` enum value in `src/dhow/core/types.py`.
2. Add a factory method in `src/dhow/core/field.py`.
3. Map it to a SQLAlchemy column in `src/dhow/engines/persistence.py`.
4. Map it to a TypeScript type in `src/dhow/core/compiler.py`.
5. Add tests in `tests/test_doctype.py` and `tests/test_persistence.py`.

## Adding an emitter

Emitters live in `src/dhow/core/compiler.py`. Follow the pattern:

```python
class MyEmitter:
    def emit(self, registry: Registry) -> str:
        ...
```

Register it in `emit_all()` and add a test in `tests/test_compiler.py`.

## Coding conventions

- `from __future__ import annotations` in every Python file.
- Type hints on public functions.
- Docstrings in Google style (short one-liners for simple helpers).
- Use `Path` from `pathlib` for filesystem paths.
- Prefer dataclasses over raw dicts for internal structures.

## License

MIT — see `LICENSE`.
