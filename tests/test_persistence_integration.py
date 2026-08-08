"""Integration tests against a live Postgres database.

Requires a running Postgres server and DHOW_TEST_DATABASE_URL.
"""

import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from dhow import DocType, field
from dhow.core.compiler import compile_registry
from dhow.engines.audit import audit_trigger_function_sql as audit_trigger_sql
from dhow.engines.persistence import build_models, rls_policy_sql, set_tenant_sql
from dhow.engines.sequences import create_sequence_sql, sequence_name

DATABASE_URL = os.getenv(
    "DHOW_TEST_DATABASE_URL", "postgresql+asyncpg://dhow:dhow@localhost:5432/dhow"
)

pytestmark = pytest.mark.asyncio


async def _database_reachable() -> bool:
    try:
        engine = create_async_engine(DATABASE_URL, future=True, echo=False)
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        await engine.dispose()
        return True
    except Exception:
        return False


@pytest_asyncio.fixture
async def db_engine():
    if not await _database_reachable():
        pytest.skip("Postgres database is not reachable")
    engine = create_async_engine(DATABASE_URL, future=True, echo=False)
    async with engine.begin() as conn:
        await conn.execute(text("CREATE SCHEMA IF NOT EXISTS public"))
    yield engine
    await engine.dispose()


class Customer(DocType):
    name = field.Text(required=True)


class Invoice(DocType):
    number = field.Sequence(prefix="INV-")
    customer = field.Link("Customer", required=True)
    total = field.Decimal(required=True)


async def test_create_invoice(db_engine):
    registry = compile_registry([Customer, Invoice])
    models = build_models(registry)
    metadata = next(iter(models.values())).metadata

    async with db_engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(metadata.create_all)
        await conn.execute(text(audit_trigger_sql()))

    async_session = sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        async with session.begin():
            await session.execute(text(set_tenant_sql(str(uuid.uuid4()))))
            customer = models["Customer"](name="Acme")
            session.add(customer)
            await session.flush()

            seq = sequence_name("Invoice", "number", str(customer.tenant_id))
            await session.execute(text(create_sequence_sql(seq)))
            next_number = await session.execute(text(f"SELECT nextval('{seq}')"))
            invoice = models["Invoice"](
                number=f"INV-{next_number.scalar()}",
                customer=str(customer.id),
                total=100.00,
            )
            session.add(invoice)
            await session.flush()

        assert invoice.id is not None
        assert invoice.tenant_id == customer.tenant_id


@pytest.mark.skipif(
    not os.getenv("DHOW_TEST_DATABASE_URL"),
    reason="Live database test only when DHOW_TEST_DATABASE_URL is set",
)
async def test_rls_blocks_cross_tenant_read(db_engine):
    tenant_a = str(uuid.uuid4())
    tenant_b = str(uuid.uuid4())

    registry = compile_registry([Customer])
    models = build_models(registry)
    metadata = next(iter(models.values())).metadata
    table_name = models["Customer"].__tablename__

    async with db_engine.begin() as conn:
        await conn.run_sync(metadata.drop_all)
        await conn.run_sync(metadata.create_all)
        await conn.execute(text(audit_trigger_sql()))
        for statement in rls_policy_sql(table_name):
            await conn.execute(text(statement))

    async_session = sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with async_session() as session:
        async with session.begin():
            await session.execute(text(set_tenant_sql(tenant_a)))
            customer_a = models["Customer"](name="Tenant A")
            session.add(customer_a)
            await session.flush()

            await session.execute(text(set_tenant_sql(tenant_b)))
            result = await session.execute(text(f"SELECT id FROM {table_name}"))
            rows = result.all()
            assert len(rows) == 0
