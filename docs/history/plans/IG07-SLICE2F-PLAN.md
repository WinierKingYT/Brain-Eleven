# IG-07 Slice 2F — `task_state_context.py` Migration Plan

**Durum:** CLOSED / SHIPPED — bounded plan, implementation and regression
evidence are recorded in `docs/history/reports/IG07-SLICE2F-PACKAGE-REPORT.md` (2026-09-17).
**Kapsam:** yalnız `scripts/task_state_context.py` implementation inversion and
its direct callers; task model, state resolver, registry, router, authority,
retrieval and persistence semantics are frozen.
**Hedef:** `brain_eleven/runtime/task_state_context.py` canonical implementation.
**Compatibility surface:** `scripts/task_state_context.py` and bare
`task_state_context` remain importable adapters during the compatibility
window.

This slice is the deliberately separate follow-up to IG-07 Slice 2E. The
module has the widest blast radius in the inventory, so the implementation is
gated by an explicit caller inventory, contract tests and CLI/fail-closed
evidence before the adapter is changed.

## 1. Baseline and caller inventory

The inventory method follows `IG07-SLICE2-PLAN.md`: count unique Python files
outside the target modules that contain an actual AST import of
`task_state_context`; comments, docstrings, coverage path strings and
`conftest.py`'s dynamic bare-module alias are metadata, not runtime callers.
The current source scan produced **26 files / 26 caller edges**:

### Production and evaluation callers — 14

| Caller | Edge |
|---|---|
| `brain_eleven/runtime/context.py` | relative package import |
| `context_router/__main__.py` | `scripts.task_state_context` |
| `context_compiler_v2/shadow.py` | local runtime import |
| `authority/shadow.py` | `scripts.task_state_context` |
| `authority/serialization.py` | local decoder import |
| `evals/authority_evaluation.py` | `scripts.task_state_context` |
| `evals/authority_provider.py` | `scripts.task_state_context` |
| `evals/compiler_v2_benchmark.py` | `scripts.task_state_context` |
| `evals/compiler_v2_evaluation.py` | `scripts.task_state_context` |
| `evals/compiler_v2_provider.py` | `scripts.task_state_context` |
| `evals/router_benchmark.py` | `scripts.task_state_context` |
| `evals/router_evaluation.py` | `scripts.task_state_context` |
| `evals/router_provider.py` | `scripts.task_state_context` |
| `evals/runtime_provider.py` | `scripts.task_state_context` |

### Behavioral test callers — 12

`tests/context_engine/test_foundation_pipeline.py`,
`tests/test_authority_resolver.py`, `tests/test_context_compiler_v2.py`,
`tests/test_context_compiler_v2_hardening.py`,
`tests/test_context_engine_operational_surfaces.py`,
`tests/test_context_router.py`, `tests/test_pre13_runtime.py`,
`tests/test_task_state_context.py`, `tests/test_tsc01_timezone.py`,
`tests/test_tsc02_identity.py`, `tests/test_w22_optional_omission.py` and
`tests/test_canonical_runtime_boundaries.py`.

The target's own definition and the following non-runtime references are
excluded from the 26: `scripts/task_state_context.py`,
`brain_eleven/runtime/task_state_context.py`, `conftest.py`,
`scripts/check_context_engine_coverage.py`, `tests/test_context_engine_coverage.py`,
`evals/ig01d/fingerprint.py` and `evals/w09a/evaluation.py`.

### Scope boundaries

In scope:

- Move the existing `TaskStateLineageError`, `TaskStateLineage`,
  `TaskStateContext`, `TaskStateComposer`, constants and `main` implementation
  into `brain_eleven.runtime.task_state_context`.
- Make package imports the implementation authority and make the script a
  thin compatibility/direct-execution adapter.
- Migrate direct production/evaluation imports to the package surface where
  doing so does not remove a required historical bare import.
- Preserve the compatibility identity of package, `scripts.*` and bare
  `task_state_context` objects.
- Add structural, fixture, identity, CLI and fail-closed regression evidence.

Out of scope:

- Any new task/state fields, schema version, lineage policy or routing policy.
- Changes to `brain_eleven/runtime/task.py`, `StateResolver`,
  `ProjectRegistry`, router, authority, retrieval, compiler or persistence.
- New persistence, registration, auto-repair, retrieval or LLM behavior.
- Changes to evaluation labels, holdout files, thresholds or coverage policy.
- Removal of the compatibility adapter or the bare test alias.

## 2. Canonical implementation and adapter contract

The package owns one implementation. It may import only the package surfaces
for task, state resolver and project identity. It must not import
`scripts.task_state_context`, `scripts.task_model` or another legacy
implementation.

The script adapter may only:

1. bootstrap the repository root for direct execution;
2. import and cache `brain_eleven.runtime.task_state_context`;
3. re-export the historical constants, classes, exception and `main` names;
4. preserve the `scripts.task_state_context` / bare `task_state_context`
   module identity expected by old callers;
5. delegate `python scripts/task_state_context.py ...` to canonical `main`.

It may not define a second dataclass/class/function implementation, perform
JSON/file persistence, mutate a registry/state/memory authority, or contain an
alternative CLI.

## 3. Invariants to freeze before implementation

### Task and state composition

- `TASK_STATE_CONTEXT_SCHEMA_VERSION` remains `1`.
- `TaskStateContext.to_dict()` keeps the exact ordered top-level keys
  `schema_version`, `task`, `state`, `lineage`.
- The task envelope remains the canonical `TaskEnvelope` from
  `brain_eleven.runtime.task`; its schema, deterministic analyzer rules,
  project-resolution status and exception identity do not change.
- State remains the read-only `CurrentProjectState` from
  `brain_eleven.state.resolver`; all resolver statuses and bounded error
  strings are passed through unchanged.
- State constraints already present in the task's explicit constraints are
  not duplicated. New inherited constraints are stable and order-preserving.
- `active_blockers` and valid `state_references` add their existing context
  needs once; all context needs remain stable and de-duplicated.

### Lineage and fail-closed behavior

- `resolved` lineage contains only a valid project ID, non-negative registry
  revision and opaque `project-root-v1:` identity.
- `unresolved` and `global` lineage contain no project identity fields.
- A registry change between the initial and final read raises
  `TaskStateLineageError`; a mixed task/state context is never published.
- Unknown, archived, relocated, reused-root and corrupt-registry behavior
  remains explicit and fail-closed. No error may expose a filesystem path,
  raw secret or raw malformed payload.
- Composition performs no write, registration, repair, cache, retrieval or
  routing operation.

### Import and CLI parity

- Package, `scripts.task_state_context` and bare `task_state_context` expose
  the same object identities for all public names, including the
  `TaskStateContext`/`TaskStateLineage` dataclasses and `main`.
- The adapter and `python -m brain_eleven.runtime.task_state_context` emit the
  same JSON/text contract, ignoring only generated task ID and timestamp when
  comparing process output.
- Existing direct callers continue to work without adding a `scripts/`
  `sys.path` injection.

## 4. Ordered work gates

1. **Plan/inventory:** this document and the 26-file AST inventory are fixed.
2. **Contract tests:** add identity, package-owned AST, adapter-only AST,
   fixture/lineage parity, CLI and fail-closed tests before changing the
   adapter.
3. **Implementation inversion:** move the existing implementation verbatim
   in behavior to the package and change only its dependency imports.
4. **Compatibility adapter:** replace the script body with a thin canonical
   loader/re-export/direct-execution adapter; migrate direct production and
   evaluation imports to the package boundary.
5. **Focused validation:** run task-state, TSC-01/TSC-02, caller-boundary,
   router/authority/compiler and CLI/copy smoke tests.
6. **Full validation:** run compile, diff hygiene and the repository baseline
   suite excluding only the established integration/graduation selection and
   the pre-existing W06C0R1 contract exclusion. Record exact counts and any
   unrelated warnings in the package report.

## 5. Exit criteria

Slice 2F is complete only when all of these are true:

- canonical package source contains the implementation and no direct legacy
  import edge;
- the legacy script is adapter-only by AST and historical imports remain
  object-identical;
- all 26 caller files are accounted for and direct production/evaluation
  callers use the package surface where scoped;
- valid, unknown, archived, corrupt, lineage-race and malformed-input
  fixtures preserve the pre-inversion behavior;
- CLI JSON/text and fail-closed output are verified without path/content
  leakage;
- focused tests, compile and full regression pass;
- a package report records the exact validation evidence.

If an invariant cannot be preserved without a second authority or a scope
expansion, stop the inversion and record `RETHINK/defer`; do not tune fixtures
or weaken the fail-closed contract.
