"""Tests for workspace/app discovery and per-app command loading."""

from __future__ import annotations

from pathlib import Path

from dhow_cli.workspace import AppContract, Workspace, discover_workspace, write_apps_list


def test_discovers_workspace_by_apps_and_sites(tmp_path: Path) -> None:
    apps = tmp_path / "apps"
    sites = tmp_path / "sites"
    apps.mkdir()
    sites.mkdir()
    (apps / "dhow").mkdir()
    (sites / "apps.txt").write_text("dhow\n", encoding="utf-8")

    ws = discover_workspace(tmp_path)
    assert ws is not None
    assert ws.root == tmp_path
    assert ws.apps == ["dhow"]


def test_discovers_workspace_walks_upward(tmp_path: Path) -> None:
    apps = tmp_path / "apps"
    sites = tmp_path / "sites"
    apps.mkdir()
    sites.mkdir()
    (sites / "apps.txt").write_text("dhow\n", encoding="utf-8")
    nested = tmp_path / "sites" / "my-site" / "public"
    nested.mkdir(parents=True)

    ws = discover_workspace(nested)
    assert ws is not None
    assert ws.root == tmp_path


def test_app_contract_parsed_from_dhow_toml(tmp_path: Path) -> None:
    apps = tmp_path / "apps"
    app_source = apps / "dhow_erp"
    app_source.mkdir(parents=True)
    app_source.joinpath("dhow.toml").write_text(
        '[app]\nname = "dhow_erp"\ntitle = "Dhow ERP"\nversion = "0.1.0"\n'
        '[framework]\nversion = ">=0.2.0,<0.3.0"\n'
        '[modules]\naccounting = "dhow_erp.accounting"\n'
        '[commands]\ninstall = "dhow_erp.setup.install:install"\n'
        '[hooks]\nafter_migrate = ["dhow_erp.patches.apply_post_migration"]\n',
        encoding="utf-8",
    )

    contract = AppContract(
        app_name="dhow_erp",
        title="Dhow ERP",
        version="0.1.0",
        publisher="",
        description="",
        license="",
        framework_version=">=0.2.0,<0.3.0",
        modules={"accounting": "dhow_erp.accounting"},
        commands={"install": "dhow_erp.setup.install:install"},
        hooks={"after_migrate": ["dhow_erp.patches.apply_post_migration"]},
        doctypes={},
        raw={},
        path=app_source / "dhow.toml",
        source_path=app_source,
    )
    assert contract.commands["install"] == "dhow_erp.setup.install:install"


def test_write_apps_list(tmp_path: Path) -> None:
    sites = tmp_path / "sites"
    sites.mkdir()
    ws = Workspace(
        root=tmp_path,
        apps_path=tmp_path / "apps",
        sites_path=sites,
        config_path=tmp_path / "dhow.toml",
        apps=["dhow", "dhow_erp"],
        app_contracts={},
    )
    write_apps_list(ws, ["dhow", "dhow_erp"])
    assert (sites / "apps.txt").read_text(encoding="utf-8") == "dhow\ndhow_erp\n"
