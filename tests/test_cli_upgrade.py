"""CLI smoke tests for `dhow test-upgrade`.

The command is a thin wrapper over
:func:`dhow.engines.upgrade.assert_upgrade_safe`. These tests pin
down the contract: ``--corpus`` is required, ``--json`` is supported,
drift raises a non-zero exit, and the JSON summary aggregates every
scenario.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from typer.testing import CliRunner

from dhow_cli.main import app

runner = CliRunner()


CORPUS_PATH = Path("/tmp/dhow-fw/tests/fixtures/upgrade_corpus.json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_corpus(scenarios: list[dict]) -> Path:
    """Write a one-off corpus to a tmp file and return the path."""
    import tempfile

    fd = tempfile.NamedTemporaryFile(
        "w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump({"scenarios": scenarios}, fd)
    fd.flush()
    fd.close()
    return Path(fd.name)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_test_upgrade_command_succeeds_against_committed_corpus() -> None:
    result = runner.invoke(
        app,
        ["test-upgrade", "--corpus", str(CORPUS_PATH)],
    )
    assert result.exit_code == 0, result.output
    assert "2/2 safe" in result.output
    assert str(CORPUS_PATH) in result.output


def test_test_upgrade_command_json_summary() -> None:
    result = runner.invoke(
        app,
        ["test-upgrade", "--corpus", str(CORPUS_PATH), "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["ok"] is True
    assert payload["safe"] == 2
    assert payload["unsafe"] == 0
    assert payload["total"] == 2
    assert payload["corpus"] == str(CORPUS_PATH)
    assert {s["name"] for s in payload["scenarios"]} == {
        "framework_adds_new_doctype",
        "layer_adds_field_to_existing_doctype",
    }
    for entry in payload["scenarios"]:
        assert entry["safe"] is True
        assert entry["drift"] == {"missing": [], "unexpected": [], "changed": []}


# ---------------------------------------------------------------------------
# Drift reporting
# ---------------------------------------------------------------------------


def test_test_upgrade_command_reports_missing_step_drift() -> None:
    corpus_path = _write_corpus(
        [
            {
                "name": "phantom",
                "base_registry": {"doctypes": {}},
                "layer_set": [],
                "target_registry": {"doctypes": {}},
                "expected_migrations": [
                    {
                        "name": "framework.create_table.invoice",
                        "version": "1",
                        "kind": "create_table",
                        "target": "Invoice",
                        "source": "framework",
                        "layer": None,
                    }
                ],
            }
        ]
    )
    try:
        result = runner.invoke(
            app,
            ["test-upgrade", "--corpus", str(corpus_path), "--json"],
        )
        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["ok"] is False
        assert "phantom" in payload["error"]
        assert "Missing" in payload["error"]
        assert "framework.create_table.invoice" in payload["error"]
    finally:
        corpus_path.unlink()


def test_test_upgrade_command_reports_unexpected_step_drift() -> None:
    corpus_path = _write_corpus(
        [
            {
                "name": "surprise",
                "base_registry": {"doctypes": {}},
                "layer_set": [],
                "target_registry": {
                    "doctypes": {
                        "Order": {
                            "name": "Order",
                            "version": "1",
                            "fields": [{"name": "total", "kind": "decimal"}],
                        }
                    }
                },
                "expected_migrations": [],
            }
        ]
    )
    try:
        result = runner.invoke(
            app,
            ["test-upgrade", "--corpus", str(corpus_path)],
        )
        assert result.exit_code == 1
        assert "Unexpected" in result.output
        assert "framework.create_table.order" in result.output
    finally:
        corpus_path.unlink()


def test_test_upgrade_command_text_mode_prints_drift() -> None:
    corpus_path = _write_corpus(
        [
            {
                "name": "first",
                "base_registry": {"doctypes": {}},
                "layer_set": [],
                "target_registry": {"doctypes": {}},
                "expected_migrations": [],
            },
            {
                "name": "second_breaks",
                "base_registry": {"doctypes": {}},
                "layer_set": [],
                "target_registry": {
                    "doctypes": {
                        "Order": {
                            "name": "Order",
                            "version": "1",
                            "fields": [{"name": "total", "kind": "decimal"}],
                        }
                    }
                },
                "expected_migrations": [
                    {
                        "name": "framework.create_table.invoice",
                        "version": "1",
                        "kind": "create_table",
                        "target": "Invoice",
                        "source": "framework",
                        "layer": None,
                    }
                ],
            },
        ]
    )
    try:
        result = runner.invoke(
            app,
            ["test-upgrade", "--corpus", str(corpus_path)],
        )
        assert result.exit_code == 1
        assert "after 1 clean" in result.output
        assert "'second_breaks'" in result.output
    finally:
        corpus_path.unlink()


# ---------------------------------------------------------------------------
# Argument validation
# ---------------------------------------------------------------------------


def test_test_upgrade_command_missing_corpus_option() -> None:
    result = runner.invoke(app, ["test-upgrade"])
    assert result.exit_code != 0
    # Typer prints a "Missing option" error to stderr; we only care that
    # the command rejected the missing --corpus argument.
    assert "--corpus" in (result.output + (result.stderr or "")) or result.exit_code == 2


def test_test_upgrade_command_missing_file() -> None:
    result = runner.invoke(
        app,
        ["test-upgrade", "--corpus", "/nonexistent/corpus.json", "--json"],
    )
    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["ok"] is False
    assert payload["corpus"] == "/nonexistent/corpus.json"
    assert "not found" in payload["error"].lower()


def test_test_upgrade_command_malformed_corpus() -> None:
    bad = Path("/tmp") / "dhow_bad_corpus_for_cli.json"
    bad.write_text("not json", encoding="utf-8")
    try:
        result = runner.invoke(
            app,
            ["test-upgrade", "--corpus", str(bad), "--json"],
        )
        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["ok"] is False
        assert "not valid JSON" in payload["error"]
    finally:
        bad.unlink(missing_ok=True)


def test_test_upgrade_command_missing_scenarios_key() -> None:
    bad = Path("/tmp") / "dhow_no_scenarios_for_cli.json"
    bad.write_text(json.dumps({"items": []}), encoding="utf-8")
    try:
        result = runner.invoke(
            app,
            ["test-upgrade", "--corpus", str(bad), "--json"],
        )
        assert result.exit_code == 1
        payload = json.loads(result.output)
        assert payload["ok"] is False
        assert "'scenarios'" in payload["error"]
    finally:
        bad.unlink(missing_ok=True)
