from dhow import DocType, field
from dhow.core.compiler import compile_registry
from dhow.engines.persistence import (
    attach_audit_trigger_sql,
    audit_trigger_sql,
    build_models,
    rls_policy_sql,
    set_tenant_sql,
)


class Invoice(DocType):
    number = field.Sequence(prefix="INV-", immutable=True)
    total = field.Computed("sum(lines.amount)", store=True)


def test_build_models_from_registry():
    registry = compile_registry([Invoice])
    models = build_models(registry)
    assert "Invoice" in models
    model = models["Invoice"]
    assert model.__tablename__ == "dt_invoice"
    assert hasattr(model, "id")
    assert hasattr(model, "tenant_id")
    assert hasattr(model, "number")


def test_rls_policy_sql():
    statements = rls_policy_sql("dt_invoice")
    sql = " ".join(statements)
    assert "ENABLE ROW LEVEL SECURITY" in sql
    assert "FORCE ROW LEVEL SECURITY" in sql
    assert "current_setting('app.tenant_id')" in sql


def test_set_tenant_sql():
    import uuid
    tenant_id = str(uuid.uuid4())
    sql = set_tenant_sql(tenant_id)
    assert tenant_id in sql


def test_audit_trigger_sql():
    sql = audit_trigger_sql()
    assert "CREATE OR REPLACE FUNCTION public.dhow_audit_trigger" in sql
    assert "INSERT INTO public.dhow_audit" in sql


def test_attach_audit_trigger_sql():
    sql = attach_audit_trigger_sql("dt_invoice")
    assert "CREATE TRIGGER dt_invoice_audit" in sql
    assert "EXECUTE FUNCTION public.dhow_audit_trigger" in sql
