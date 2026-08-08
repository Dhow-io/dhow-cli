"""Generate a FastAPI application from a Dhow registry."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, create_model

from dhow.core.registry import Registry
from dhow.core.types import FieldKind, Operation
from dhow.engines.execute import DhowEngine, engine
from dhow.engines.permissions import Actor


def _pydantic_field(field: Any) -> tuple[type, Any]:
    """Map a Dhow Field to a Pydantic field tuple (type, default)."""
    mapping: dict[FieldKind, type] = {
        FieldKind.TEXT: str,
        FieldKind.INT: int,
        FieldKind.DECIMAL: float,
        FieldKind.DATE: str,
        FieldKind.DATETIME: str,
        FieldKind.BOOL: bool,
        FieldKind.JSON: dict[str, Any],
        FieldKind.LINK: str,
        FieldKind.SEQUENCE: str,
        FieldKind.STATE: str,
        FieldKind.COMPUTED: float,
    }
    py_type = mapping.get(field.kind, str)
    if not field.required:
        return (py_type | None, None)
    return (py_type, ...)


def _make_request_model(entry: Any) -> type[BaseModel]:
    fields: dict[str, tuple[type, Any]] = {}
    for field in entry.fields.values():
        if field.kind == FieldKind.TABLE:
            continue
        # Sequence values are generated server-side; don't require them on create.
        if field.kind == FieldKind.SEQUENCE:
            fields[field.name] = (str | None, None)
        else:
            fields[field.name] = _pydantic_field(field)
    return create_model(f"{entry.name}Create", **fields)


def _make_response_model(entry: Any) -> type[BaseModel]:
    fields: dict[str, tuple[type, Any]] = {}
    for field in entry.fields.values():
        if field.kind == FieldKind.TABLE:
            continue
        if field.kind == FieldKind.SEQUENCE:
            fields[field.name] = (str | None, None)
        else:
            fields[field.name] = _pydantic_field(field)
    fields["id"] = (UUID, ...)
    fields["tenant_id"] = (UUID, ...)
    return create_model(f"{entry.name}Response", **fields)


def _current_actor(request: Request) -> Actor:
    """Build an Actor from request state / headers. Stub: reads X-User-Id and X-Roles."""
    user_id = request.headers.get("x-user-id", "anonymous")
    roles_header = request.headers.get("x-roles", "guest")
    tenant_id = request.headers.get("x-tenant-id")
    return Actor(
        user_id=user_id,
        roles=tuple(r.strip() for r in roles_header.split(",") if r.strip()),
        tenant_id=tenant_id,
    )


def _make_handlers(
    dhow: DhowEngine,
    doctype_name: str,
    create_model_cls: type[BaseModel],
    response_model_cls: type[BaseModel],
) -> dict[str, Any]:
    """Create endpoint handler functions with concrete annotations in their globals."""
    namespace: dict[str, Any] = {
        "Depends": Depends,
        "UUID": UUID,
        "HTTPException": HTTPException,
        "Operation": Operation,
        "Actor": Actor,
        "dhow": dhow,
        "doctype_name": doctype_name,
        "CreateModel": create_model_cls,
        "ResponseModel": response_model_cls,
        "_current_actor": _current_actor,
    }

    exec(
        """
async def list_docs(
    actor: Actor = Depends(_current_actor),
) -> list[ResponseModel]:
    result = await dhow.execute(Operation.READ, actor, doctype_name)
    if not result.ok:
        raise HTTPException(status_code=403, detail=result.error)
    return []

async def create_doc(
    payload: CreateModel,
    actor: Actor = Depends(_current_actor),
) -> ResponseModel:
    result = await dhow.execute(
        Operation.CREATE, actor, doctype_name, data=payload.model_dump()
    )
    if not result.ok:
        raise HTTPException(status_code=403, detail=result.error)
    return ResponseModel(
        **payload.model_dump(exclude_unset=True),
        id=UUID(int=0),
        tenant_id=UUID(int=0),
    )

async def get_doc(
    doc_id: UUID,
    actor: Actor = Depends(_current_actor),
) -> ResponseModel:
    result = await dhow.execute(Operation.READ, actor, doctype_name, doc_id=str(doc_id))
    if not result.ok:
        raise HTTPException(status_code=403, detail=result.error)
    return ResponseModel(id=doc_id, tenant_id=UUID(int=0))

async def update_doc(
    doc_id: UUID,
    payload: CreateModel,
    actor: Actor = Depends(_current_actor),
) -> ResponseModel:
    result = await dhow.execute(
        Operation.UPDATE, actor, doctype_name, data=payload.model_dump(), doc_id=str(doc_id)
    )
    if not result.ok:
        raise HTTPException(status_code=403, detail=result.error)
    return ResponseModel(**payload.model_dump(), id=doc_id, tenant_id=UUID(int=0))

async def delete_doc(
    doc_id: UUID,
    actor: Actor = Depends(_current_actor),
) -> dict[str, Any]:
    result = await dhow.execute(Operation.DELETE, actor, doctype_name, doc_id=str(doc_id))
    if not result.ok:
        raise HTTPException(status_code=403, detail=result.error)
    return {"ok": True, "deleted": doc_id}

async def submit_doc(
    doc_id: UUID,
    actor: Actor = Depends(_current_actor),
) -> dict[str, Any]:
    result = await dhow.execute(Operation.SUBMIT, actor, doctype_name, doc_id=str(doc_id))
    if not result.ok:
        raise HTTPException(status_code=403, detail=result.error)
    return {"ok": True, "submitted": doc_id}
""",
        namespace,
    )
    return {
        "list": namespace["list_docs"],
        "create": namespace["create_doc"],
        "get": namespace["get_doc"],
        "update": namespace["update_doc"],
        "delete": namespace["delete_doc"],
        "submit": namespace["submit_doc"],
    }


def create_app(registry: Registry) -> FastAPI:
    """Build a FastAPI app exposing CRUD + transitions for every DocType."""
    app = FastAPI(title="Dhow API", version="0.2.0")
    dhow = engine(registry)

    for entry in registry.doctypes.values():
        create_model_cls = _make_request_model(entry)
        response_model_cls = _make_response_model(entry)
        doctype_name = entry.name
        base = f"/{doctype_name.lower()}"

        handlers = _make_handlers(dhow, doctype_name, create_model_cls, response_model_cls)

        app.get(base, response_model=list[response_model_cls])(handlers["list"])
        app.post(base, response_model=response_model_cls)(handlers["create"])
        app.get(base + "/{doc_id}", response_model=response_model_cls)(handlers["get"])
        app.patch(base + "/{doc_id}", response_model=response_model_cls)(handlers["update"])
        app.delete(base + "/{doc_id}")(handlers["delete"])
        app.post(base + "/{doc_id}/submit")(handlers["submit"])

    return app


def generate_app_source(registry: Registry, output_path: Any) -> None:
    """Generate a standalone app module file (placeholder)."""
    output_path.write_text(
        "# Auto-generated Dhow FastAPI app\nfrom dhow.generated.app import create_app\n",
        encoding="utf-8",
    )
