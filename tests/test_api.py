"""Tests for the generated FastAPI API."""

from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from dhow import DocType, field
from dhow.core.compiler import compile_registry
from dhow.core.registry import Registry
from dhow.generators.api import create_app


class Invoice(DocType):
    number = field.Sequence(prefix="INV-")
    total = field.Decimal(required=True)

    permissions = {"read": "all", "create": "clerk", "submit": "manager"}


@pytest.fixture
def client():
    registry = compile_registry([Invoice])
    app = create_app(registry)
    return TestClient(app)


def test_list_invoices_requires_auth(client):
    # Default actor has role 'guest' which can read because read = all
    response = client.get("/invoice", headers={"X-Roles": "guest"})
    assert response.status_code == 200
    assert response.json() == []


def test_create_invoice_authorized(client):
    response = client.post(
        "/invoice",
        json={"total": 100.00},
        headers={"X-Roles": "clerk"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 100.00
    assert "id" in data


def test_create_invoice_denied_for_guest(client):
    response = client.post(
        "/invoice",
        json={"total": 100.00},
        headers={"X-Roles": "guest"},
    )
    assert response.status_code == 403


def test_submit_invoice_requires_manager(client):
    response = client.post(
        "/invoice/00000000-0000-0000-0000-000000000000/submit",
        headers={"X-Roles": "manager"},
    )
    assert response.status_code == 200


def test_submit_invoice_denied_for_clerk(client):
    response = client.post(
        "/invoice/00000000-0000-0000-0000-000000000000/submit",
        headers={"X-Roles": "clerk"},
    )
    assert response.status_code == 403
