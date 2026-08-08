"""Single chokepoint: every data operation routes through engine.execute()."""

from __future__ import annotations

from typing import Any

from dhow.core.registry import Registry
from dhow.core.types import Operation
from dhow.engines.permissions import Actor, PermissionEngine, PermissionError


class OperationResult:
    """Result wrapper returned by engine.execute()."""

    def __init__(self, ok: bool, data: Any = None, error: str | None = None):
        self.ok = ok
        self.data = data
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return {"ok": self.ok, "data": self.data, "error": self.error}


class DhowEngine:
    """Facade that combines permission checks with persistence operations."""

    def __init__(self, registry: Registry):
        self.registry = registry
        self.permissions = PermissionEngine(registry)

    async def execute(
        self,
        operation: Operation | str,
        actor: Actor,
        doctype_name: str,
        data: dict[str, Any] | None = None,
        doc_id: str | None = None,
    ) -> OperationResult:
        """Single chokepoint for all data access."""
        data = data or {}
        try:
            self.permissions.check(actor, doctype_name, operation)
        except PermissionError as exc:
            return OperationResult(ok=False, error=str(exc))

        op = Operation(operation) if isinstance(operation, str) else operation
        if op in {Operation.CREATE, Operation.UPDATE}:
            filtered = self.permissions.filter_fields(actor, doctype_name, op, data)
        else:
            filtered = data

        # Persistence and workflow hooks will plug in here.
        return OperationResult(
            ok=True,
            data={
                "doctype": doctype_name,
                "operation": op.value,
                "doc_id": doc_id,
                "fields": filtered,
                "actor_role": actor.effective_role(),
            },
        )


def engine(registry: Registry) -> DhowEngine:
    return DhowEngine(registry)
