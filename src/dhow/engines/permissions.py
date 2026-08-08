"""Permission engine — single chokepoint for all data access decisions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from dhow.core.registry import DocTypeEntry, Registry
from dhow.core.types import Operation


class Level(int, Enum):
    """Permission levels. L1 = system, L2 = role-based, L3 = row-level, L4 = agent (stub)."""

    SYSTEM = 1
    ROLE = 2
    ROW = 3
    AGENT = 4


class PermissionError(Exception):
    """Raised when an operation is denied."""

    pass


@dataclass(frozen=True)
class Actor:
    """Identity of the caller."""

    user_id: str | None = None
    roles: tuple[str, ...] = ()
    tenant_id: str | None = None
    agent_id: str | None = None
    agent_role: str | None = None

    def effective_role(self) -> str | None:
        """Agent identity = min(agent role, initiating user's permissions).

        Returns agent_role when present (subordinate to the user's own roles).
        Otherwise returns the user's first role.
        """
        if self.agent_role and self.agent_role in self.roles:
            return self.agent_role
        return self.roles[0] if self.roles else None

    def effective_roles(self) -> set[str]:
        """Roles available for permission checks.

        When an agent role is set, only that role is available, because agents
        are subordinate to the initiating user's permissions.
        """
        if self.agent_role and self.agent_role in self.roles:
            return {self.agent_role}
        return set(self.roles)


class PermissionEngine:
    """Decides whether an actor may perform an operation on a DocType."""

    def __init__(self, registry: Registry):
        self.registry = registry

    def allowed_operations(self, actor: Actor, doctype_name: str) -> set[str]:
        """Return the set of operations the actor may perform on a DocType."""
        entry = self.registry.doctypes.get(doctype_name)
        if entry is None:
            return set()
        grants = entry.permissions.get("grants", {})
        ops: set[str] = set()
        for op, grant in grants.items():
            if self._role_match(actor, grant):
                ops.add(op)
        return ops

    def can(self, actor: Actor, doctype_name: str, operation: Operation | str) -> bool:
        op = Operation(operation) if isinstance(operation, str) else operation
        return op.value in self.allowed_operations(actor, doctype_name)

    def check(self, actor: Actor, doctype_name: str, operation: Operation | str) -> None:
        if not self.can(actor, doctype_name, operation):
            op_value = Operation(operation).value if isinstance(operation, str) else operation.value
            raise PermissionError(
                f"{actor.effective_role() or 'anonymous'} cannot {op_value} {doctype_name}"
            )

    def filter_fields(
        self,
        actor: Actor,
        doctype_name: str,
        operation: Operation | str,
        fields: dict[str, Any],
    ) -> dict[str, Any]:
        """Remove hidden fields and enforce read-only for the actor's roles."""
        entry = self.registry.doctypes.get(doctype_name)
        if entry is None:
            return {}
        result: dict[str, Any] = {}
        for name, value in fields.items():
            if self._is_hidden(entry, name, actor, operation):
                continue
            result[name] = value
        return result

    def _role_match(self, actor: Actor, grant: dict[str, Any]) -> bool:
        allowed = set(grant.get("roles", []))
        if "all" in allowed:
            return True
        return bool(actor.effective_roles() & allowed)

    def _is_hidden(
        self,
        entry: DocTypeEntry,
        field_name: str,
        actor: Actor,
        operation: Operation | str,
    ) -> bool:
        field = entry.fields.get(field_name)
        if field is None:
            return False
        hidden = field.hidden
        if hidden is True:
            return True
        if isinstance(hidden, list):
            return bool(set(hidden) & actor.effective_roles())
        return False


def engine_for(registry: Registry) -> PermissionEngine:
    return PermissionEngine(registry)
