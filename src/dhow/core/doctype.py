"""DocType authoring API: base class, metaclass, and field factory."""

from __future__ import annotations

from typing import Any, Callable

from dhow.core.controls import ImmutableAfter
from dhow.core.permissions import PermissionSet
from dhow.core.types import Field, FieldKind
from dhow.core.workflow import Approval, StateMachine


class DocTypeMeta(type):
    """Collects field declarations and declarative blocks on DocType subclasses."""

    def __new__(
        mcs,
        name: str,
        bases: tuple[type, ...],
        namespace: dict[str, Any],
        **kwargs: Any,
    ) -> "DocTypeMeta":
        if name == "DocType":
            return super().__new__(mcs, name, bases, namespace, **kwargs)

        fields: dict[str, Field] = {}
        workflow: Approval | StateMachine | None = None
        controls: list[Any] = []
        permissions_decl: dict[str, Any] | None = None

        for attr_name, value in list(namespace.items()):
            if isinstance(value, Field):
                fields[attr_name] = value.with_name(attr_name)
                # Replace the descriptor in the class namespace so the type remains clean.
                namespace[attr_name] = value.with_name(attr_name)
            elif isinstance(value, (Approval, StateMachine)):
                workflow = value
            elif isinstance(value, ImmutableAfter):
                controls.append(value)
            elif attr_name == "permissions":
                permissions_decl = value
            elif attr_name == "controls":
                controls.extend(value if isinstance(value, list) else [value])
            elif attr_name == "workflow":
                if isinstance(value, (Approval, StateMachine)):
                    workflow = value

        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        cls._dhow_fields = fields
        cls._dhow_workflow = workflow
        cls._dhow_controls = controls
        cls._dhow_permissions = PermissionSet.from_decl(permissions_decl)
        cls._dhow_name = name
        return cls


class DocType(metaclass=DocTypeMeta):
    """Base class for all Dhow DocTypes."""

    _dhow_name: str
    _dhow_fields: dict[str, Field]
    _dhow_workflow: Approval | StateMachine | None
    _dhow_controls: list[Any]
    _dhow_permissions: PermissionSet

    @classmethod
    def dhow_meta(cls) -> dict[str, Any]:
        return {
            "name": cls._dhow_name,
            "fields": [f.to_dict() for f in cls._dhow_fields.values()],
            "workflow": cls._dhow_workflow.to_dict() if cls._dhow_workflow else None,
            "controls": [c.to_dict() for c in cls._dhow_controls],
            "permissions": cls._dhow_permissions.to_dict(),
        }


_COMMON_KWARGS = frozenset(
    {"index", "unique", "default", "immutable", "label", "hidden", "read_only"}
)


def _split_options(options: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Split kwargs into Field attributes and kind-specific options."""
    attrs = {k: options.pop(k) for k in list(options.keys()) if k in _COMMON_KWARGS}
    return attrs, options


class FieldFactory:
    """Public `field.*` factory methods.

    Both snake_case and PascalCase aliases are exposed so the documented
    example syntax (`field.Text(...)`) works unchanged.
    """

    # Snake_case canonical methods
    def text(self, *, required: bool = False, **options: Any) -> Field:
        attrs, opts = _split_options(options)
        return Field(kind=FieldKind.TEXT, required=required, options=opts, **attrs)

    def int(self, *, required: bool = False, **options: Any) -> Field:
        attrs, opts = _split_options(options)
        return Field(kind=FieldKind.INT, required=required, options=opts, **attrs)

    def decimal(self, *, required: bool = False, **options: Any) -> Field:
        attrs, opts = _split_options(options)
        return Field(kind=FieldKind.DECIMAL, required=required, options=opts, **attrs)

    def date(self, *, required: bool = False, **options: Any) -> Field:
        attrs, opts = _split_options(options)
        return Field(kind=FieldKind.DATE, required=required, options=opts, **attrs)

    def datetime(self, *, required: bool = False, **options: Any) -> Field:
        attrs, opts = _split_options(options)
        return Field(kind=FieldKind.DATETIME, required=required, options=opts, **attrs)

    def bool(self, *, required: bool = False, **options: Any) -> Field:
        attrs, opts = _split_options(options)
        return Field(kind=FieldKind.BOOL, required=required, options=opts, **attrs)

    def sequence(
        self,
        *,
        prefix: str = "",
        immutable: bool = True,
        required: bool = True,
        **options: Any,
    ) -> Field:
        attrs, opts = _split_options(options)
        attrs.setdefault("immutable", immutable)
        return Field(
            kind=FieldKind.SEQUENCE,
            required=required,
            options={"prefix": prefix, **opts},
            **attrs,
        )

    def link(
        self,
        target_doctype: str,
        *,
        required: bool = False,
        index: bool = True,
        **options: Any,
    ) -> Field:
        attrs, opts = _split_options(options)
        attrs.setdefault("index", index)
        return Field(
            kind=FieldKind.LINK,
            required=required,
            options={"target_doctype": target_doctype, **opts},
            **attrs,
        )

    def table(
        self,
        child_doctype: str,
        *,
        required: bool = False,
        **options: Any,
    ) -> Field:
        attrs, opts = _split_options(options)
        return Field(
            kind=FieldKind.TABLE,
            required=required,
            options={"child_doctype": child_doctype, **opts},
            **attrs,
        )

    def state(self, states: list[str], *, required: bool = True, **options: Any) -> Field:
        attrs, opts = _split_options(options)
        return Field(
            kind=FieldKind.STATE,
            required=required,
            options={"states": states, **opts},
            **attrs,
        )

    def computed(
        self,
        expr: str,
        *,
        store: bool = True,
        index: bool = False,
        **options: Any,
    ) -> Field:
        attrs, opts = _split_options(options)
        attrs.setdefault("index", index)
        return Field(
            kind=FieldKind.COMPUTED,
            required=False,
            options={"expr": expr, "store": store, **opts},
            **attrs,
        )

    def json(self, *, required: bool = False, **options: Any) -> Field:
        attrs, opts = _split_options(options)
        return Field(kind=FieldKind.JSON, required=required, options=opts, **attrs)

    # PascalCase aliases matching the documented API examples
    Text = text
    Int = int
    Decimal = decimal
    Date = date
    DateTime = datetime
    Bool = bool
    Sequence = sequence
    Link = link
    Table = table
    State = state
    Computed = computed
    JSON = json


field: FieldFactory = FieldFactory()


def workflow(value: Approval | StateMachine) -> Approval | StateMachine:
    """Decorator / assignment helper for workflows."""
    return value


def control(*items: Any) -> list[Any]:
    """Helper to declare a list of controls."""
    return list(items)
