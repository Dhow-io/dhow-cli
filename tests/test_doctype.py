"""Tests for the DocType authoring API."""

import pytest

from dhow import DocType, field, workflow
from dhow.core.controls import ImmutableAfter
from dhow.core.types import FieldKind
from dhow.core.workflow import Approval, StateMachine


class Customer(DocType):
    name = field.Text(required=True)
    email = field.Text(index=True)
    active = field.Bool(default=True)


class Invoice(DocType):
    number = field.Sequence(prefix="INV-", immutable=True)
    customer = field.Link("Customer", required=True, index=True)
    date = field.Date(default="today", required=True)
    lines = field.Table("InvoiceLine", required=True)
    status = field.State(["draft", "submitted", "paid", "cancelled"])
    total = field.Computed("sum(lines.amount)", store=True, index=True)

    workflow = workflow.Approval(threshold={"total > 100000": "finance_manager"})
    controls = [ImmutableAfter("submitted")]
    permissions = {
        "read": "all",
        "create": "ar_clerk",
        "submit": "ar_clerk",
    }


def test_customer_fields_collected():
    meta = Customer.dhow_meta()
    names = {f["name"] for f in meta["fields"]}
    assert names == {"name", "email", "active"}


def test_invoice_field_kinds():
    fields = {f["name"]: f for f in Invoice.dhow_meta()["fields"]}
    assert fields["number"]["kind"] == FieldKind.SEQUENCE.value
    assert fields["number"]["options"]["prefix"] == "INV-"
    assert fields["number"]["immutable"] is True
    assert fields["customer"]["kind"] == FieldKind.LINK.value
    assert fields["customer"]["options"]["target_doctype"] == "Customer"
    assert fields["lines"]["kind"] == FieldKind.TABLE.value
    assert fields["lines"]["options"]["child_doctype"] == "InvoiceLine"
    assert fields["status"]["kind"] == FieldKind.STATE.value
    assert fields["status"]["options"]["states"] == ["draft", "submitted", "paid", "cancelled"]
    assert fields["total"]["kind"] == FieldKind.COMPUTED.value
    assert fields["total"]["options"]["expr"] == "sum(lines.amount)"
    assert fields["total"]["index"] is True


def test_invoice_workflow_and_controls():
    meta = Invoice.dhow_meta()
    assert meta["workflow"]["kind"] == "approval"
    assert meta["workflow"]["thresholds"] == {"total > 100000": "finance_manager"}
    assert len(meta["controls"]) == 1
    assert meta["controls"][0]["kind"] == "immutable_after"
    assert meta["controls"][0]["state_field"] == "submitted"


def test_invoice_permissions():
    meta = Invoice.dhow_meta()
    grants = meta["permissions"]["grants"]
    assert grants["read"]["roles"] == ["all"]
    assert grants["create"]["roles"] == ["ar_clerk"]
    assert grants["submit"]["roles"] == ["ar_clerk"]


def test_field_label_default():
    meta = Customer.dhow_meta()
    fields = {f["name"]: f for f in meta["fields"]}
    assert fields["name"]["label"] == "Name"


def test_field_roundtrip():
    from dhow.core.types import Field

    original = field.Decimal(required=True).with_name("rate")
    restored = Field.from_dict(original.to_dict())
    assert restored.kind == FieldKind.DECIMAL
    assert restored.name == "rate"
    assert restored.required is True


def test_state_machine_workflow():
    class Task(DocType):
        title = field.Text(required=True)
        status = field.State(["todo", "doing", "done"])

        workflow = StateMachine(
            states=["todo", "doing", "done"],
            transitions={"todo": ["doing"], "doing": ["done", "todo"]},
        )

    meta = Task.dhow_meta()
    assert meta["workflow"]["kind"] == "state_machine"
    assert meta["workflow"]["initial"] == "todo"
    assert meta["workflow"]["transitions"]["doing"] == ["done", "todo"]
