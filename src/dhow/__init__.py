"""Dhow — a metadata-driven declarative Python framework for AI-native ERP."""

__version__ = "0.2.0"

from dhow.core.doctype import DocType, field
from dhow.core.workflow import Approval, StateMachine, Workflow
from dhow.core.controls import ImmutableAfter
from dhow.core.permissions import PermissionSet

# Expose a workflow namespace object so both the declaration
# `workflow = workflow.Approval(...)` and `workflow.Approval(...)` work.
workflow = Workflow()

__all__ = [
    "DocType",
    "field",
    "Approval",
    "StateMachine",
    "ImmutableAfter",
    "PermissionSet",
    "workflow",
]
