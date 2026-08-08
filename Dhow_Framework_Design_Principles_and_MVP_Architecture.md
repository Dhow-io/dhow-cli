# Dhow Framework: Design Principles & MVP Architecture

## A Metadata-Driven Declarative Framework for AI-Native ERP

*Named after the dhow — the historic sailing vessel of the East African coast and Indian Ocean trade routes, connecting Africa, Arabia, and Asia in commerce for centuries. The framework plays the same connective role: between business data, AI agents, and the people who run them.*

**Naming & identity (checked 2026-08-06):**

| Asset | Handle | Status |
|---|---|---|
| PyPI package | `dhow` | ✅ Available — claim immediately (placeholder 0.0.1) |
| CLI command | `dhow` | Primary developer interface |
| Python import | `from dhow import DocType, ...` | — |
| GitHub org | `dhow-framework` | ✅ Available (bare `dhow` held by a 2013 personal account) |
| npm | `dhow-framework` (or scoped `@dhow/*` later) | ✅ Available (bare `dhow` taken by a 2020 package) |
| Brand | **"Dhow Framework"** | Use the full name in docs/marketing to avoid collision with the unrelated npm/GitHub `dhow` packages |

**Companion to:** *Deep Research Report on Open-Source ERP Systems*
**Working name:** Dhow
**Date:** 2026-08-06

---

## Table of Contents

1. Purpose and Positioning
2. The Seven Non-Negotiable Design Principles
3. The Decision Menu — Conscious Choices, Not a Buffet
4. Core Architecture
5. The Metadata Dual-Representation Model (the key innovation)
6. The Customization Engine (customization as data)
7. Permissions, Workflow, Audit & Control Engines
8. The AI Layer Interface
9. API and UI Generation
10. Migration & Versioning
11. The CLI (`dhow`)
12. MVP Scope and Phasing
13. Anti-Scope (What the Framework Will NOT Do)
14. Risks and Mitigations
15. Success Criteria

---

## 1. Purpose and Positioning

Dhow is the framework layer of the AI-native ERP described in the research report. It synthesizes the lessons of three mature predecessors:

| Incumbent | What we take | What we avoid |
|---|---|---|
| **Frappe** | Metadata-as-data at runtime; auto-generated Desk UI; AI-readable schema | Runtime magic opacity; MariaDB lock-in; hard static analysis |
| **Odoo** | Typed Python model definitions; IDE ergonomics; ORM inheritance | Customization-as-code → upgrade breakage; AI as bolt-on |
| **OFBiz** | Total model/code separation; declarative services | XML verbosity; leaky abstraction; developer-hostile UX |

**Positioning statement:** Dhow is a framework in which the *core is code* (typed, static, reviewable) and *customization is data* (declarative, upgrade-safe, AI-generatable) — with permissions, workflow, audit, controls, and agent interfaces as first-class engine features rather than retrofits.

---

## 2. The Seven Non-Negotiable Design Principles

These are the guard against second-system syndrome. Any proposed feature that violates one of these is rejected, no matter how attractive.

**P1 — Customization is always data; the core is always code.**
End-user and partner extensions (fields, forms, workflows, control rules, reports) live in the metadata registry as data — never as framework patches. The framework core is typed Python under normal code review. This is the single most important principle: it simultaneously delivers Odoo-grade developer ergonomics and Frappe-grade runtime extensibility without either's downside.

**P2 — Metadata compiles to inspectable artifacts; no unexplained magic.**
Every metadata definition *generates concrete, readable artifacts* — migration SQL, TypeScript types, OpenAPI specs, permission tables — checked into version control or viewable in a dev console. If a developer cannot answer "what did the framework actually do?" in under a minute, the design has failed.

**P3 — The database is PostgreSQL, and integrity lives there.**
FKs, check constraints, unique constraints, SERIALIZABLE for sensitive transactions, RLS for row-level multi-tenancy, append-only audit via triggers. The framework never reimplements in application code what PostgreSQL enforces natively.

**P4 — Every entity operation is automatically a typed, permissioned API.**
Creating a DocType (Dhow's model unit) automatically yields: REST endpoints, an MCP tool definition, a permission matrix entry, an audit hook, and an event-bus topic. No extra code. AI agents and human users traverse the *same* validated path.

**P5 — Agents are first-class but subordinate.**
Agent identities exist natively in the permission system, always derived from and capped by the initiating user's permissions. Agents propose; the engine disposes. Write operations are confirmable drafts by default.

**P6 — Upgrades never break customization.**
Because customization is data (P1), framework upgrades migrate metadata forward — they cannot collide with user extensions. This is a testable CI guarantee: every release runs upgrade tests against a corpus of real customization registries.

**P7 — Human gates are runtime primitives.**
Approval, escalation, and confirmation are built into the workflow/run lifecycle (resumable checkpoints), not bolted on per feature. Any AI or automation action can be declared `requires_approval` in metadata.

---

## 3. The Decision Menu — Conscious Choices, Not a Buffet

For each axis, we pick one point deliberately instead of claiming both extremes.

| Axis | Choice | Rationale |
|---|---|---|
| Where metadata lives | **Authored in typed Python, compiled into a DB registry** | Static analysis + runtime queryability both (§5) |
| Static vs dynamic | **Core static; customization dynamic** | The only point on the spectrum that serves both developers and AI safely |
| Magic vs explicit | **Explicit artifacts, generated automatically** | P2: generation yes, invisible runtime behavior no |
| ORM style | **Thin composition layer over SQLAlchemy; no deep inheritance chains** | Odoo's `_inherit` chains are the root of its fragility; prefer composition (mixins with explicit resolution order) |
| UI generation | **Opinionated auto-generated defaults + declared overrides** | Frappe Desk's lesson: 90% of screens are standard; the 10% get declarative escape hatches, never code forks |
| Multi-tenancy | **RLS + tenant_id on every table (shared schema)** | Schema-per-tenant breaks migration economics at scale; RLS is enforced in PG itself (P3) |
| Metadata changes at runtime | **Allowed, but through the same migration pipeline as code changes** | No silent in-place ALTERs; even runtime customization generates a versioned migration (§10) |
| Query interface | **Structured query builder + semantic layer; never raw SQL from AI** | Report §6: text-to-SQL is a sandboxed fallback, not the primary path |

---

## 4. Core Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  Auto-generated UI (React/TS)                                  │
│  Desk: forms, lists, kanban, reports  +  Conversational shell │
├──────────────────────────────────────────────────────────────┤
│  Interface layer                                               │
│  REST/OpenAPI  ·  MCP tool server  ·  GraphQL (optional)      │
├──────────────────────────────────────────────────────────────┤
│  Dhow Engine                                                   │
│  ├─ Metadata registry (compiled DocType definitions)          │
│  ├─ Persistence (SQLAlchemy → PostgreSQL)                     │
│  ├─ Permission engine (RBAC + field-level + RLS bridge)       │
│  ├─ Workflow engine (states, transitions, approval matrix)    │
│  ├─ Control engine (SoD, matching, period locks — metadata)   │
│  ├─ Audit engine (append-only, trigger-written)               │
│  ├─ Event bus (every mutation publishes an event)             │
│  └─ Agent runtime bridge (identity derivation, draft/commit)  │
├──────────────────────────────────────────────────────────────┤
│  PostgreSQL 16+  (RLS · SSI · pgvector · append-only audit)   │
│  Redis (cache/queue)  ·  Object storage (attachments)          │
└──────────────────────────────────────────────────────────────┘
```

Every box inside "Dhow Engine" is a **separate engine with a defined contract**, not a tangle — this is the direct fix for the Frappe opacity complaint (report §14.2).

---

## 5. The Metadata Dual-Representation Model (the key innovation)

The central design: **one DocType, two faces.**

### 5.1 Authoring face (code — for developers)

```python
from dhow import DocType, field, workflow, control

class Invoice(DocType):
    # fields: typed, IDE-completable, statically analyzable
    number     = field.Sequence(prefix="INV-", immutable=True)
    customer   = field.Link("Customer", required=True, index=True)
    date       = field.Date(default="today", required=True)
    currency   = field.Link("Currency", required=True)
    lines      = field.Table("InvoiceLine", required=True)
    status     = field.State(["draft", "submitted", "paid", "cancelled"])
    total      = field.Computed("sum(lines.amount)", store=True, index=True)

    # declarative behavior — no code forks needed for standard cases
    workflow   = workflow.Approval(threshold={"total > 100000": "finance_manager"})
    controls   = [
        control.ImmutableAfter("submitted"),                 # P3: trigger-enforced
        control.RequireDualReview(on_change="customer.bank_account"),
    ]
    permissions = {"read": "all", "create": "ar_clerk", "submit": "ar_clerk"}
```

### 5.2 Registry face (data — for runtime, AI, and tooling)

On `dhow build`, every DocType compiles into the **metadata registry** — versioned rows in PostgreSQL:

```json
{
  "doctype": "Invoice", "version": 14,
  "fields": [ {"name": "customer", "type": "Link", "target": "Customer",
               "required": true, "index": true}, ... ],
  "workflow": {"type": "approval", "thresholds": [...]},
  "controls": [...], "permissions": {...},
  "generated": {"migration": "migrations/014_invoice.sql",
                "openapi_fragment": "...", "mcp_tool": "invoice.create"}
}
```

The registry is the **single source of truth at runtime**: the UI generator, REST/MCP layer, permission engine, and AI agents all read it. It is also what makes the system *self-describing* — an agent (or a new developer) can query `registry` and learn the entire application schema, terminology, and rules without reading source code. This is the answer to both Frappe's opacity problem and the AI-readability requirement.

### 5.3 Why not pure Frappe-style (JSON-only) or pure Odoo-style (code-only)?

- JSON-only loses type checking, refactoring, and code review (every framework error surfaces at runtime).
- Code-only cannot be safely modified at runtime — which AI-driven module generation requires.
- Dual representation costs one compiler step (`dhow build`) and buys both. The compiler is ~the complexity of a schema migration tool — bounded, testable, deterministic.

---

## 6. The Customization Engine (customization as data)

All non-developer extensions flow through one mechanism: **customization layers** — JSON patches to registry entries, namespaced and ordered.

```json
{
  "layer": "acme_corp", "target": "Invoice", "version_base": 14,
  "add_fields": [{"name": "purchase_order_ref", "type": "Link", "target": "PurchaseOrder"}],
  "add_controls": [{"type": "Approval", "when": "total > 50000", "role": "cfo"}],
  "ui_overrides": {"list_columns": ["number", "customer", "total", "purchase_order_ref"]}
}
```

Rules:
1. **Layers stack deterministically**: framework core → industry pack → partner → tenant. Conflicts resolve by layer order, explicitly logged.
2. **Layers never modify the core's code or core field semantics** — they can add, not mutate (a tenant cannot weaken a framework control; they can only add stricter ones). This makes upgrades collision-free (P6).
3. **Layers are versioned, diffable, exportable** — a tenant's entire customization state is one exportable artifact (dev → staging → prod promotion, partner solution packaging).
4. **AI generates layers, not code.** When the design agent creates a new DocType or control rule from natural language (report §7.2), its output is a *draft layer* entering the approval workflow — never a code commit.

---

## 7. Permissions, Workflow, Audit & Control Engines

### 7.1 Permission engine

Four levels, all metadata-declared, all enforced twice (application + PostgreSQL RLS where applicable):

```
Level 1  Role-based       (role → DocType → read/create/update/delete/submit)
Level 2  Field-level      (role → DocType → field → read/write/hidden)
Level 3  Row-level        (rules → PG RLS policies: "own branch", "own company")
Level 4  Agent-level      (agent identity = min(agent role, initiating user's permissions))
```

Enforcement is a single chokepoint — `engine.execute(operation)` — that every interface (UI, REST, MCP, background job, agent) must traverse. There is no second path to the database.

### 7.2 Workflow engine

States and transitions declared in metadata; transitions carry guards (`total > X`), approval requirements, and side effects (post journal, reserve stock). Human approvals are **resumable checkpoints** — a document sits in `pending_approval` indefinitely, with escalation rules, and resumes on decision (P7).

### 7.3 Audit engine

- Every mutation writes an append-only audit record (who, when, old→new values, source interface, agent-identity-if-any, approval chain) via PostgreSQL triggers — captures even direct SQL access.
- Audit schema is write-once: no UPDATE/DELETE grants exist for any role, including superusers (P3).
- Agent actions carry the full provenance chain: initiating user → agent run ID → tool call → prompt hash.

### 7.4 Control engine

The internal-controls substrate from report §7, implemented as **metadata-declared rules evaluated by a deterministic executor**:

| Control type | Mechanism |
|---|---|
| Immutability (posted documents) | DB trigger + engine check |
| SoD (mutually exclusive actions on one document) | Rule table + executor at transition time |
| Three-way matching | Rule + tolerance config, evaluated on submit |
| Approval matrix | Workflow engine thresholds |
| Period locks | Guard on all financial transitions |
| Master-data dual review | Workflow gate on sensitive field changes |

**The AI design agent's only interface to controls is proposing draft rules** — which enter the same approval workflow as any other sensitive change. The executor itself is small (~deterministic rule evaluation), auditable, and never contains model calls (report §13: governance below the model layer).

---

## 8. The AI Layer Interface

The framework exposes itself to the harness (Deep Agents / Claude Agent SDK — report §13.2) through exactly four channels:

1. **MCP tool server (generated)** — every DocType operation auto-published as a typed MCP tool with the permission matrix attached. Tool exposure is role-scoped (an AP clerk's agent never sees GL-posting tools — report §13.2, Vercel finding).
2. **Registry introspection tools** — `describe_doctype`, `search_schema`, `glossary_lookup` give agents structured access to the metadata registry and business glossary (the semantic layer's foundation).
3. **Query interface** — semantic-layer metrics first; sandboxed text-to-SQL fallback with validation, read-only role, EXPLAIN caps (report §6.3).
4. **Draft/commit bridge** — agents create drafts; commit requires the permission and (where declared) human approval. All agent writes are indistinguishable in audit from human writes except richer provenance.

The framework also ships **Agent Skills** (report §13.1): SKILL.md packages for the glossary, posting rules, close procedures, and control-design playbooks — versioned, reviewed, progressively disclosed.

---

## 9. API and UI Generation

**API**: from the registry, `dhow build` emits OpenAPI 3.1 specs and MCP tool manifests. Typed TypeScript client generated for the frontend. Breaking schema changes are compiler errors, not runtime surprises.

**UI**: an opinionated React/TypeScript generator producing the Desk-equivalent:
- List views (from `list_columns` + sensible defaults), forms (layout from field grouping metadata), kanban (from state fields), print formats (from template metadata).
- Declarative overrides via customization layers — never code forks (P1).
- Every generated screen includes the conversational shell entry point (the AI assistant knows the current DocType context automatically — the registry makes this trivial).

The UI generator is scoped as a first-class workstream (§11), honoring the "UI tax" lesson from report §14.

---

## 10. Migration & Versioning

- **Every schema change is an explicit migration** — generated by the metadata compiler, reviewable, reversible. Applies equally to code-authored DocTypes and runtime customization layers: changing a layer *generates a migration*, which is what gets applied (no in-place magic ALTERs ever — P2).
- **Registry versioning**: every registry entry carries a version; layers declare `version_base`; the engine detects base/layer drift and reports it (instead of Odoo-style silent breakage).
- **Tenant migration pipeline**: `dhow migrate --tenant acme` computes framework diff + layer diffs → one ordered migration plan → applies in a transaction-safe sequence with rollback points.
- **Data migrations** (opening balances, imports) are framework-declared scripts with validation hooks — the migration-wizard wedge (report §14.5) builds directly on this.

---

## 11. The CLI (`dhow`)

*Added 2026-08-06.*

The CLI is not an accessory — it is the **execution backbone of P2 (inspectable artifacts) and P6 (upgrade safety)**. The dual-representation model has no compiler without `dhow build`; the migration pipeline has no runner without `dhow migrate`; CI has no enforcement point without `dhow build --check`. It is the single tool through which developers, CI pipelines, and AI agents interact with the framework's mechanics.

### 11.1 Hard design rules

1. **The CLI contains no logic.** Every command is a one-to-one mapping onto a documented engine API. If logic appears in a command handler, it belongs in an engine, exposed uniformly to CLI, REST, and MCP. (This is the discipline that prevents the Frappe `bench` failure mode: years of accreted commands with inconsistent semantics.)
2. **`--json` is first-class on every command.** This makes the CLI a ready-made MCP tool source — agents get structured, permission-aware access to framework mechanics (§8, channel 2) without a second integration layer. `dhow describe`, `dhow schema search`, and `dhow diff` *are* the agent introspection surface.
3. **Built on a mature CLI framework** (Typer/Click) — engineering effort goes into the compiler and migration engine behind the commands, not argument parsing.

### 11.2 Command surface (by lifecycle)

**Project scaffolding**
```bash
dhow init my-erp                        # new project: structure, config, Docker compose (PG/Redis)
dhow new module accounting              # scaffold a module with conventional layout
dhow new doctype Invoice --module ar    # typed Python stub with conventional fields
```

**The compile step (the heart)**
```bash
dhow build                              # DocType Python → registry rows + artifacts:
                                       #   migrations/*.sql, openapi.json, mcp_tools.json,
                                       #   TypeScript types, permission tables
dhow build --check                      # dry-run: fails CI on code/registry drift (enforces P2)
dhow diff                               # show what a change would generate (terraform-plan style)
```

**Migrations & environments**
```bash
dhow migrate                            # apply pending migrations (framework + layers, ordered)
dhow migrate --tenant acme              # per-tenant migration plan with rollback points
dhow migrate --rollback to=v14          # reverse to a named point
dhow import-data opening_balances.csv --map auto   # migration-wizard surface (report §14.5 wedge)
```

**Customization layers**
```bash
dhow layer new acme_corp                # scaffold a customization layer
dhow layer diff acme_corp               # layer vs base-version drift report (P6 diagnostics)
dhow layer export acme_corp -o acme.json   # dev → staging → prod promotion artifact
dhow layer validate                     # reject weakening of framework controls (§6 rule 2)
```

**Registry introspection (dual-purpose: humans and agents)**
```bash
dhow describe Invoice                   # fields, permissions, workflow, controls — from registry
dhow schema search "payment"            # semantic search over registry + glossary
dhow doctor                             # environment/permissions/migration health check
```

**Dev loop & ops**
```bash
dhow serve                              # dev server with hot rebuild of registry
dhow worker / dhow scheduler             # background jobs (event bus consumers, CCM scans)
dhow seed --demo                        # demo tenant with realistic data
dhow test                               # framework + module + upgrade tests (P6 corpus)
```

### 11.3 Delivery phasing

- **Phase 0**: `init`, `new`, `build` (+`--check`, `diff`), `migrate`, `describe` — the minimum that makes P2/P6 real.
- **Phase 1**: `layer *`, `import-data`, `seed`, `serve`, `doctor`, `test`.
- **Phase 2+**: `worker`/`scheduler`, tenant operations, packaging/publishing of layers and Skills.

---

## 12. MVP Scope and Phasing

**MVP definition: framework + three modules + AI query, deployed for one pilot tenant.**

| Phase | Deliverable | Duration (4–6 senior engineers) |
|---|---|---|
| **0 — Foundation** | DocType compiler, metadata registry, SQLAlchemy persistence, migration pipeline, permission engine L1–L3 | 4–6 months |
| **1 — Surface** | REST/OpenAPI generation, UI generator (list/form), auth, audit engine, event bus | 4–6 months |
| **2 — Modules** | Accounting (GL, journal immutability, period locks), Inventory (stock moves, SERIALIZABLE deduction), Purchasing (PO→receipt→invoice, 3-way match via control engine) | 6–9 months |
| **3 — AI layer** | MCP tool server, registry introspection, semantic layer v1 (20–30 core metrics), sandboxed text-to-SQL fallback, draft/commit bridge, conversational shell in Desk | 4–6 months (parallel with Phase 2) |
| **4 — Pilot** | One anchor tenant (report §15: Kenya candidate), migration wizard v1, hardening | 3 months |

**Total to pilot: ~18–24 months.** Everything else (HR/payroll, manufacturing, multi-company, localization packs, control-design agent, CCM agent, fine-tuning pipeline) is post-pilot, sequenced by pilot feedback.

**Deliberately excluded from MVP** (to protect the schedule): no plugin marketplace, no visual low-code designer, no multi-company consolidation, no payroll, no mobile app (responsive web first), no offline sync v1.

---

## 12. Anti-Scope (What the Framework Will NOT Do)

Explicit rejections, to prevent scope creep and second-system syndrome:

1. **No general-purpose app platform** — Dhow serves ERP-shaped (transactional, document-centric) applications. It will not chase Retool-style arbitrary CRUD apps.
2. **No multi-database support** — PostgreSQL only (P3). "Database agnostic" is how OFBiz lost integrity guarantees.
3. **No runtime code execution from metadata** — customization layers can add fields/rules/layout, never executable code. (Escapes: server-side extension points in versioned code, under review.)
4. **No deep ORM inheritance** — composition only.
5. **No AI in the deterministic engines** — permission, control, audit, and posting executors contain zero model calls.
6. **No maximal autonomy** — agents default to least agency (report §13.2); autonomy expansion is per-tenant configuration, not the default.

---

## 13. Risks and Mitigations

| Risk | Severity | Mitigation |
|---|---|---|
| Second-system syndrome (trying to be everything) | High | P1–P7 principles; anti-scope §12; any principle-violating feature rejected |
| UI tax underestimated | High | UI generator is a dedicated Phase-1 workstream with its own owner; pilot on real users early |
| Metadata migration edge cases at scale | Medium-High | Explicit migrations only; upgrade-test corpus from pilot tenants in CI (P6) |
| ORM pathological queries (N+1) | Medium | Query-composition discipline in persistence layer; built-in query profiler from Phase 0 |
| Dual representation drift (code vs registry) | Medium | `dhow build` is the only writer of the registry; CI fails on any drift |
| Two products at once (framework + ERP) | High | MVP slicing (§11); framework ships only what the three modules need |
| Team velocity (small team, large surface) | High | AI-assisted development (the harness builds the framework that hosts the harness); ruthless anti-scope |
| Community/ecosystem cold start | Medium | Open-source from Phase 1; registry/Skill format documented as the contribution surface |

---

## 14. Success Criteria

The framework is succeeding when, at pilot + 6 months:

1. A new DocType (say, `FixedAsset`) can be added by a developer in < 1 day with auto-generated UI, API, MCP tools, permissions, audit — and *zero* framework changes.
2. A tenant customization layer survives a framework minor upgrade with zero breakage (CI-verified).
3. An AI agent can answer "what fields does Invoice have and who can edit them?" entirely from registry introspection — and act on it within permissions.
4. Every document in the pilot tenant has a complete provenance chain (human or agent) in the audit log, with zero un-audited mutation paths.
5. Text-to-SQL fallback handles pilot users' ad-hoc questions at ≥ 85% accuracy with 0 silent-failure reports (wrong-but-plausible results) — measured by the feedback flywheel.
6. A new developer can become productive in the codebase in < 2 weeks (the anti-Frappe-opacity metric).

---

*This document defines the framework layer only. Business-module specifications, localization packs, and the agent Skill library are separate companion documents to be written after Phase 0.*
