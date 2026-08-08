# Dhow Framework — Bootstrap Prompt

Use this prompt with an AI coding assistant (Claude Code, Cursor, or similar) to bootstrap the Dhow framework and CLI.

**Before pasting:** attach both companion documents to the session:
1. `Open_Source_ERP_Deep_Research_Report.md`
2. `Dhow_Framework_Design_Principles_and_MVP_Architecture.md`

Then paste the prompt below. Execute one Step at a time and review output before proceeding.

---

```
You are building "Dhow Framework" — a metadata-driven declarative Python framework 
for AI-native ERP, designed per these non-negotiable principles:

P1 — Customization is always DATA (JSON layers in a registry); the core is always CODE (typed Python).
P2 — Metadata compiles to inspectable artifacts (SQL migrations, OpenAPI, TS types, MCP tools). No runtime magic.
P3 — PostgreSQL-only. Integrity enforced in the DB (FKs, CHECK constraints, RLS, SERIALIZABLE, trigger-written append-only audit).
P4 — Every DocType automatically yields: REST endpoints, MCP tool definitions, permission entries, audit hooks, event topics.
P5 — Agents are first-class but subordinate: agent identity = min(agent role, initiating user's permissions). Agents create drafts; humans commit.
P6 — Upgrades never break customization. Customization layers are additive-only, versioned against base versions.
P7 — Human approval gates are resumable workflow checkpoints, not afterthoughts.

## Build Order (strictly sequential — do not skip ahead)

### Step 1: Project skeleton
- Python 3.12+, src layout: `src/dhow/{core,engines,cli}/`
- Dependencies: SQLAlchemy 2.x (async), asyncpg, Typer, Pydantic v2, Alembic, Redis
- Docker Compose: PostgreSQL 16 (+pgvector), Redis
- `dhow init <name>` scaffolds a project with this structure

### Step 2: The DocType authoring API (core compiler input)
Implement `dhow.core.doctype`:
- `DocType` base class with a metaclass that collects field declarations
- Field types: `Text, Int, Decimal, Date, DateTime, Bool, Sequence(prefix=, immutable=), 
  Link(target_doctype), Table(child_doctype), State([...]), Computed(expr, store=), JSON`
- Field options: `required, index, unique, default, immutable, label, hidden`
- Declarative blocks: `permissions = {...}`, `workflow = Approval(...)`, `controls = [...]`
- Example target syntax:

    from dhow import DocType, field, workflow, control

    class Invoice(DocType):
        number   = field.Sequence(prefix="INV-", immutable=True)
        customer = field.Link("Customer", required=True, index=True)
        date     = field.Date(default="today", required=True)
        lines    = field.Table("InvoiceLine", required=True)
        status   = field.State(["draft", "submitted", "paid", "cancelled"])
        total    = field.Computed("sum(lines.amount)", store=True, index=True)

        workflow   = workflow.Approval(threshold={"total > 100000": "finance_manager"})
        controls   = [control.ImmutableAfter("submitted")]
        permissions = {"read": "all", "create": "ar_clerk", "submit": "ar_clerk"}

### Step 3: The metadata compiler (`dhow build`)
Compile collected DocType classes into:
a) **Registry rows** (JSONB in a `dhow_registry` table, versioned per DocType) — 
   fields, permissions, workflow, controls, fully self-describing
b) **Alembic migration files** (explicit, reviewable, never in-place magic)
c) **Pydantic schemas** per DocType (for API validation)
d) **TypeScript types** (emitted to a configurable path)
e) **MCP tool manifest** (JSON: one tool per permitted operation per DocType)
`dhow build --check` exits non-zero if registry != code (drift detection).
`dhow diff` prints pending schema changes terraform-plan style.

### Step 4: Persistence engine
- SQLAlchemy models generated FROM the registry (not from the classes directly — 
  registry is the runtime source of truth)
- Every table: `id uuid pk`, `tenant_id`, `created_at/by`, `updated_at/by`
- RLS policy on every table using a `app.tenant_id` session GUC
- Sequence fields via PG sequences per (doctype, tenant)
- `immutable` and `ImmutableAfter` controls enforced via BEFORE UPDATE/DELETE triggers

### Step 5: Permission engine (Levels 1–3 for now; L4 agents later)
- Role → DocType → {read, create, update, delete, submit}
- Field-level: hidden/read-only per role
- Row-level: declared rules compiled to RLS policies
- Single chokepoint: `engine.execute(operation, actor)` — all data access routes through it

### Step 6: The CLI (Typer; --json on every command; ZERO logic in handlers — thin shell over engine APIs)
Commands: init, new module, new doctype, build, build --check, diff, migrate, 
migrate --tenant/--rollback, describe <DocType>, schema search <term>, doctor, 
serve (uvicorn), seed --demo, test

### Step 7: REST API generation
FastAPI app generated from registry: CRUD + submit/approve transitions per DocType,
auth via session, tenant scoping, all operations routed through engine.execute().

### Step 8: Audit engine
Trigger-written append-only `dhow_audit` (who, when, doctype, doc_id, action, 
old→new JSON diff, source interface, agent identity if any). 
No UPDATE/DELETE grants on the audit table for ANY role.

## Out of scope for this generation pass
UI generator, workflow checkpoint resume, customization layers, event bus, 
text-to-SQL, agents. Stub their interfaces only.

## Quality bar
- 90%+ test coverage on the compiler and permission engine
- `dhow init demo && cd demo && dhow new doctype Invoice && dhow build && dhow migrate && dhow serve` 
  must produce a working CRUD API for Invoice with audit in under 5 minutes
- Every engine has a documented public contract (docstrings + PROTOCOL.md per engine)
```

---

## Usage tips

1. **Feed the documents first**: attach both research documents before pasting the prompt — the assistant will resolve design questions against them instead of guessing.
2. **Run it stepwise**: paste the full prompt for context, but execute one Step at a time, reviewing output before proceeding. The Build Order is sequenced so each step is verifiable.
3. **The 5-minute demo command is the acceptance test** — if the generated code can't do that round trip, something structural is wrong.
