"""CLI tests for `dhow attach`, `dhow attachments list`, and `dhow attachments download`.

These tests run an in-memory SQLite metadata DB and a temp local filesystem
backend, so the full upload/list/download roundtrip is exercised without
needing a real Postgres instance. The ``DHOW_DATABASE_URL`` env var is
toggled per-test via :func:`monkeypatch.setenv` so the CLI picks up the
ephemeral database.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dhow_cli.main import app
from dhow_cli.scaffold import scaffold_project

runner = CliRunner()


def _scaffold_and_chdir(tmp_path: Path) -> Path:
    project_path = scaffold_project("demo", tmp_path / "demo")
    os.chdir(project_path)
    return project_path


def _sqlite_file_url(tmp_path: Path) -> str:
    """Return a per-test SQLite URL backed by a temp file.

    An on-disk file is required because the CLI creates a fresh
    SQLAlchemy ``Engine`` in the same process that later opens the same
    file; using ``:memory:`` would isolate the two and hide connection
    bugs.
    """
    db_path = tmp_path / "attachments.db"
    return f"sqlite:///{db_path}"


def _write_dhow_toml(project: Path, db_url: str, attachments_root: Path) -> None:
    """Rewrite the scaffolded ``dhow.toml`` so the CLI picks up our temp config."""
    config = f"""[project]
name = "demo"
version = "0.1.0"
database_url = "{db_url}"
redis_url = "redis://localhost:6379/0"

[build]
registry_path = "migrations/dhow_registry.json"
migrations_dir = "migrations/alembic"
pydantic_dir = "schemas/pydantic"
typescript_dir = "schemas/typescript"
mcp_manifest = "mcp/tools.json"

[permissions]
default_roles = ["admin", "manager", "clerk", "guest"]

[attachments]
local_root = "{attachments_root}"
"""
    (project / "dhow.toml").write_text(config, encoding="utf-8")


def test_attach_help_renders():
    result = runner.invoke(app, ["attach", "--help"])
    assert result.exit_code == 0
    assert "Upload a file" in result.output
    assert "--doctype" in result.output
    assert "--doc-id" in result.output
    assert "--json" in result.output


def test_attachments_subapp_help_lists_commands():
    result = runner.invoke(app, ["attachments", "--help"])
    assert result.exit_code == 0
    for cmd in ("list", "download"):
        assert cmd in result.output


def test_attach_missing_file_reports_error(tmp_path: Path, monkeypatch):
    project_path = _scaffold_and_chdir(tmp_path)
    db_url = _sqlite_file_url(tmp_path)
    attachments_root = tmp_path / "blobs"
    _write_dhow_toml(project_path, db_url, attachments_root)
    monkeypatch.setenv("DHOW_DATABASE_URL", db_url)

    missing = tmp_path / "does-not-exist.txt"
    result = runner.invoke(
        app,
        [
            "attach",
            str(missing),
            "--doctype",
            "Invoice",
            "--doc-id",
            "INV-1",
            "--json",
        ],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert "file" in payload["error"].lower() or "not found" in payload["error"].lower()


def test_attach_no_database_reports_clean_error(tmp_path: Path, monkeypatch):
    project_path = _scaffold_and_chdir(tmp_path)
    attachments_root = tmp_path / "blobs"
    _write_dhow_toml(project_path, "", attachments_root)
    monkeypatch.delenv("DHOW_DATABASE_URL", raising=False)
    # Remove the env var and rewrite the toml without a DB URL.
    (project_path / "dhow.toml").write_text(
        '[project]\nname = "demo"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    source = tmp_path / "doc.txt"
    source.write_bytes(b"hello attachment")

    result = runner.invoke(
        app,
        [
            "attach",
            str(source),
            "--doctype",
            "Invoice",
            "--doc-id",
            "INV-1",
            "--json",
        ],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert "database" in payload["error"].lower()


def test_attach_invalid_metadata_reports_error(tmp_path: Path, monkeypatch):
    project_path = _scaffold_and_chdir(tmp_path)
    db_url = _sqlite_file_url(tmp_path)
    attachments_root = tmp_path / "blobs"
    _write_dhow_toml(project_path, db_url, attachments_root)
    monkeypatch.setenv("DHOW_DATABASE_URL", db_url)

    source = tmp_path / "doc.txt"
    source.write_bytes(b"hello attachment")

    result = runner.invoke(
        app,
        [
            "attach",
            str(source),
            "--doctype",
            "Invoice",
            "--doc-id",
            "INV-1",
            "--metadata",
            "not-json",
            "--json",
        ],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert "metadata" in payload["error"].lower()


def test_attach_upload_records_metadata(tmp_path: Path, monkeypatch):
    project_path = _scaffold_and_chdir(tmp_path)
    db_url = _sqlite_file_url(tmp_path)
    attachments_root = tmp_path / "blobs"
    _write_dhow_toml(project_path, db_url, attachments_root)
    monkeypatch.setenv("DHOW_DATABASE_URL", db_url)

    payload_bytes = b"attachment payload bytes for the roundtrip test"
    source = tmp_path / "invoice.pdf"
    source.write_bytes(payload_bytes)

    result = runner.invoke(
        app,
        [
            "attach",
            str(source),
            "--doctype",
            "Invoice",
            "--doc-id",
            "INV-1",
            "--field",
            "receipt",
            "--content-type",
            "application/pdf",
            "--metadata",
            '{"source": "email"}',
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["doctype"] == "Invoice"
    assert payload["doc_id"] == "INV-1"
    assert payload["field"] == "receipt"
    assert payload["size_bytes"] == len(payload_bytes)
    assert payload["backend"] == "local"
    assert payload["key"] == "invoice/INV-1/invoice.pdf"
    assert payload["checksum_sha256"]
    assert payload["attachment"]["metadata"] == {"source": "email"}
    # The blob must land on disk.
    on_disk = attachments_root / "invoice" / "INV-1" / "invoice.pdf"
    assert on_disk.exists()
    assert on_disk.read_bytes() == payload_bytes


def test_attach_explicit_key(tmp_path: Path, monkeypatch):
    project_path = _scaffold_and_chdir(tmp_path)
    db_url = _sqlite_file_url(tmp_path)
    attachments_root = tmp_path / "blobs"
    _write_dhow_toml(project_path, db_url, attachments_root)
    monkeypatch.setenv("DHOW_DATABASE_URL", db_url)

    source = tmp_path / "f.bin"
    source.write_bytes(b"\x00\x01\x02\x03")

    result = runner.invoke(
        app,
        [
            "attach",
            str(source),
            "--doctype",
            "Note",
            "--doc-id",
            "N-9",
            "--key",
            "custom/path/notes.bin",
            "--json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["key"] == "custom/path/notes.bin"
    assert (attachments_root / "custom" / "path" / "notes.bin").exists()


def test_attach_human_output(tmp_path: Path, monkeypatch):
    project_path = _scaffold_and_chdir(tmp_path)
    db_url = _sqlite_file_url(tmp_path)
    attachments_root = tmp_path / "blobs"
    _write_dhow_toml(project_path, db_url, attachments_root)
    monkeypatch.setenv("DHOW_DATABASE_URL", db_url)

    source = tmp_path / "f.txt"
    source.write_bytes(b"hi")
    result = runner.invoke(
        app,
        [
            "attach",
            str(source),
            "--doctype",
            "Note",
            "--doc-id",
            "N-1",
        ],
    )
    assert result.exit_code == 0
    assert "Attached f.txt" in result.output


def test_attachments_list_empty(tmp_path: Path, monkeypatch):
    project_path = _scaffold_and_chdir(tmp_path)
    db_url = _sqlite_file_url(tmp_path)
    attachments_root = tmp_path / "blobs"
    _write_dhow_toml(project_path, db_url, attachments_root)
    monkeypatch.setenv("DHOW_DATABASE_URL", db_url)

    result = runner.invoke(
        app,
        ["attachments", "list", "--doctype", "Invoice", "--doc-id", "INV-X", "--json"],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["count"] == 0
    assert payload["attachments"] == []


def test_attachments_list_roundtrip(tmp_path: Path, monkeypatch):
    project_path = _scaffold_and_chdir(tmp_path)
    db_url = _sqlite_file_url(tmp_path)
    attachments_root = tmp_path / "blobs"
    _write_dhow_toml(project_path, db_url, attachments_root)
    monkeypatch.setenv("DHOW_DATABASE_URL", db_url)

    for name in ("a.txt", "b.txt"):
        src = tmp_path / name
        src.write_bytes(f"hello {name}".encode())
        result = runner.invoke(
            app,
            [
                "attach",
                str(src),
                "--doctype",
                "Invoice",
                "--doc-id",
                "INV-1",
                "--field",
                "receipt",
                "--json",
            ],
        )
        assert result.exit_code == 0, result.output

    result = runner.invoke(
        app,
        [
            "attachments",
            "list",
            "--doctype",
            "Invoice",
            "--doc-id",
            "INV-1",
            "--json",
        ],
    )
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["count"] == 2
    filenames = sorted(a["filename"] for a in payload["attachments"])
    assert filenames == ["a.txt", "b.txt"]


def test_attachments_list_filter_by_field(tmp_path: Path, monkeypatch):
    project_path = _scaffold_and_chdir(tmp_path)
    db_url = _sqlite_file_url(tmp_path)
    attachments_root = tmp_path / "blobs"
    _write_dhow_toml(project_path, db_url, attachments_root)
    monkeypatch.setenv("DHOW_DATABASE_URL", db_url)

    for name, field in [("a.pdf", "receipt"), ("b.pdf", "scanned")]:
        src = tmp_path / name
        src.write_bytes(b"%PDF-fake")
        result = runner.invoke(
            app,
            [
                "attach",
                str(src),
                "--doctype",
                "Invoice",
                "--doc-id",
                "INV-1",
                "--field",
                field,
                "--json",
            ],
        )
        assert result.exit_code == 0

    result = runner.invoke(
        app,
        [
            "attachments",
            "list",
            "--doctype",
            "Invoice",
            "--doc-id",
            "INV-1",
            "--field",
            "receipt",
            "--json",
        ],
    )
    payload = json.loads(result.output)
    assert payload["count"] == 1
    assert payload["attachments"][0]["filename"] == "a.pdf"


def test_attachments_download_roundtrip(tmp_path: Path, monkeypatch):
    project_path = _scaffold_and_chdir(tmp_path)
    db_url = _sqlite_file_url(tmp_path)
    attachments_root = tmp_path / "blobs"
    _write_dhow_toml(project_path, db_url, attachments_root)
    monkeypatch.setenv("DHOW_DATABASE_URL", db_url)

    payload_bytes = b"download roundtrip payload"
    source = tmp_path / "doc.bin"
    source.write_bytes(payload_bytes)

    upload = runner.invoke(
        app,
        [
            "attach",
            str(source),
            "--doctype",
            "Note",
            "--doc-id",
            "N-7",
            "--json",
        ],
    )
    assert upload.exit_code == 0
    upload_payload = json.loads(upload.output)
    attachment_id = upload_payload["attachment"]["id"]

    out = tmp_path / "out.bin"
    result = runner.invoke(
        app,
        [
            "attachments",
            "download",
            attachment_id,
            "--output",
            str(out),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    downloaded_payload = json.loads(result.output)
    assert downloaded_payload["ok"] is True
    assert downloaded_payload["size_bytes"] == len(payload_bytes)
    assert out.read_bytes() == payload_bytes


def test_attachments_download_missing_id(tmp_path: Path, monkeypatch):
    project_path = _scaffold_and_chdir(tmp_path)
    db_url = _sqlite_file_url(tmp_path)
    attachments_root = tmp_path / "blobs"
    _write_dhow_toml(project_path, db_url, attachments_root)
    monkeypatch.setenv("DHOW_DATABASE_URL", db_url)

    result = runner.invoke(
        app,
        [
            "attachments",
            "download",
            "ghost-id-00000000-0000-0000-0000-000000000000",
            "--output",
            str(tmp_path / "x.bin"),
            "--json",
        ],
    )
    assert result.exit_code != 0
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert (
        "not found" in payload["error"].lower()
        or "no such table" in payload["error"].lower()
    )
