# dhow-cli

Command-line interface for the [Dhow](https://github.com/Dhow-io/dhow) framework.

## Install

```bash
pip install dhow-cli
```

This installs both the `dhow` framework and the `dhow` command.

## Quick start

```bash
# Scaffold a new project
dhow init myapp
cd myapp

# Build metadata artifacts
dhow build

# Run the generated FastAPI app
dhow serve
```

## Commands

| Command | Description |
|---|---|
| `dhow init` | Scaffold a new Dhow project |
| `dhow new module <name>` | Create a module |
| `dhow new doctype <module> <name>` | Create a DocType under a module |
| `dhow build` | Compile DocTypes and emit registry, schemas, migrations, and manifests |
| `dhow diff` | Show pending schema changes |
| `dhow describe <doctype>` | Describe a compiled DocType |
| `dhow schema-search <term>` | Search compiled schemas |
| `dhow serve` | Run the generated FastAPI application |
| `dhow doctor` | Check project health |
| `dhow test` | Run project tests |

Every command that supports `--json` emits machine-readable output.

## Documentation

Framework documentation is in the [dhow repository](https://github.com/Dhow-io/dhow/tree/main/docs).

## License

MIT
