"""Tests for the permission engine and engine.execute chokepoint."""

import pytest

from dhow import DocType, field
from dhow.core.compiler import compile_registry
from dhow.core.types import Operation
from dhow.engines.execute import DhowEngine, engine
from dhow.engines.permissions import Actor, PermissionEngine, PermissionError


class Invoice(DocType):
    number = field.Sequence(prefix="INV-")
    total = field.Decimal(required=True)
    secret = field.Text(hidden=True)

    permissions = {
        "read": "all",
        "create": ["clerk", "manager"],
        "submit": "manager",
    }


@pytest.fixture
def registry():
    return compile_registry([Invoice])


@pytest.fixture
def perm(registry):
    return PermissionEngine(registry)


@pytest.fixture
def dhow(registry):
    return engine(registry)


def test_allowed_operations_for_manager(perm):
    manager = Actor(user_id="u1", roles=("manager",))
    ops = perm.allowed_operations(manager, "Invoice")
    assert {"read", "create", "submit"} <= ops


def test_allowed_operations_for_clerk(perm):
    clerk = Actor(user_id="u2", roles=("clerk",))
    ops = perm.allowed_operations(clerk, "Invoice")
    assert "read" in ops
    assert "create" in ops
    assert "submit" not in ops


def test_all_role_allows_read(perm):
    guest = Actor(user_id="u3", roles=("guest",))
    assert perm.can(guest, "Invoice", Operation.READ)


def test_check_raises_on_denied(perm):
    guest = Actor(user_id="u3", roles=("guest",))
    with pytest.raises(PermissionError):
        perm.check(guest, "Invoice", Operation.CREATE)


def test_hidden_field_filtered(perm):
    # Field-level hidden=True filtering happens at compile/response layer;
    # here we assert the engine removes it for read operations.
    clerk = Actor(user_id="u2", roles=("clerk",))
    fields = {"number": "INV-1", "total": 100, "secret": "hidden"}
    filtered = perm.filter_fields(clerk, "Invoice", Operation.READ, fields)
    assert "secret" not in filtered
    assert "total" in filtered


@pytest.mark.asyncio
async def test_execute_denies_unauthorized(dhow):
    guest = Actor(user_id="u3", roles=("guest",))
    result = await dhow.execute(Operation.CREATE, guest, "Invoice", {"total": 100})
    assert result.ok is False
    assert "cannot create Invoice" in result.error


@pytest.mark.asyncio
async def test_execute_allows_authorized(dhow):
    clerk = Actor(user_id="u2", roles=("clerk",))
    result = await dhow.execute(Operation.CREATE, clerk, "Invoice", {"total": 100})
    assert result.ok is True
    assert result.data["fields"]["total"] == 100


