# IG-07 Slice 2D Step D1 Independent Review

**REVIEWED REPOSITORY:** `WinierKingYT/Brain-Eleven`
**REVIEWED BRANCH:** `master`
**REVIEWED HEAD:** `c47595d` (implementation `17ed7bd`, tests `7063bc5`,
identity fix `f95ce00`, report `3a61f25`/`c47595d`)
**REVIEW DATE:** 2026-09-12
**REVIEWER:** Claude session `brain-eleven-66`
**REVIEWER ROLE:** Independent read-only reviewer
**IMPLEMENTATION PARTICIPATION:** None — implemented by Codex; this review
neither wrote nor edited `brain_eleven/memory/capture.py`,
`brain_eleven/memory/__init__.py`, `scripts/remember.py`,
`scripts/remember_opt_in.py`, or their tests.

## Method

D1 is a canonical-write migration but of a different shape than C1/C3: the
canonical write authority (`MemoryValidator.validate_single_and_append`'s
lock-based `MemoryStore.transact`) was explicitly required to stay
untouched and unduplicated, per `IG07-SLICE2D-PLAN.md` §B1. The review
therefore focused on proving the *absence* of a second write path as much
as the presence of correct behavior.

- Read `capture.py` in full and confirmed it delegates to the existing
  `MemoryValidator` rather than reimplementing any transaction logic.
- Read the adapter and the intermediate `f95ce00` fix to understand what
  compatibility gap it closed.
- Read every new test in `tests/test_memory_capture_package.py` before
  running them, particularly the concurrency and safety-ordering tests, to
  judge whether they force the properties they claim rather than merely
  asserting a happy path.
- Independently re-ran the focused suite, full suite, critical flake8,
  `compileall`, and a clean-interpreter identity check covering the
  package, adapter, bare-module, and `remember_opt_in.py` caller surfaces.
- Diffed the commit range against `install-cross-project-memory.py` (D2,
  out of scope per the C0 decision), `capture_safety.py`, `memory-validator.py`,
  and `ProjectRegistry`'s implementation to confirm none were reopened.

## No second canonical authority — verified structurally, not just by reading

`capture.py`'s `remember()` calls `MemoryValidator(str(vault)).validate_single_and_append(...)`
and returns its result; it never constructs a `MemoryStore` or calls
`.transact(...)` itself. This is enforced by a real structural test, not
just convention: `test_capture_does_not_copy_canonical_transaction_authority`
greps the *source text* of `capture.py` for `"from brain_eleven.memory.store"`,
`"MemoryStore("`, and `".transact("` and asserts none appear, while asserting
`"validate_single_and_append"` does. Independently re-read the file and
confirmed the same. The companion `test_remember_adapter_has_no_second_implementation`
does the equivalent AST/text check on the adapter script (also checking for
`json.dump`/`open(` — no direct file writes anywhere in the adapter).

## Safety-contract evidence — verified real, not just present

- **Safety-before-registry ordering**
  (`test_unsafe_capture_rejects_before_registry_access`): monkeypatches
  `ProjectRegistry` to raise `AssertionError` if constructed at all, then
  submits content containing a fake bearer token. Re-ran it: the registry is
  never touched, `accepted` is `False`, and no `validated-memory.json` is
  created. This is a genuine ordering proof, not an assumption.
- **Concurrent replay** (`test_concurrent_replay_has_one_canonical_record`):
  a real `ThreadPoolExecutor` with 2 workers submits the identical capture
  twice concurrently. Re-ran it: exactly one `created` and one
  `duplicate_returned_existing` result, one canonical record on disk. This
  exercises the actual lock inside `MemoryStore.transact`, not a simulated
  race — a stronger test than a monkeypatch-based one for this particular
  property.
- **Cross-project isolation and no path leakage**
  (`test_projects_are_isolated_and_absolute_roots_are_not_persisted`):
  identical content captured under two different absolute project roots
  gets two different `project_id`s, and the raw stored JSON text is checked
  to not contain either absolute path string. Re-ran it: passes.
- **Duplicate idempotence** (`test_duplicate_capture_does_not_change_revision_or_rebuild_graph`):
  second identical capture returns the same `memory_id`, canonical revision
  is unchanged, and the (mocked) graph builder is called exactly once
  total, not twice.

All four re-run independently, plus the identity and adapter-only tests:
**66 passed** across the focused suite.

## The `f95ce00` fix — a real compatibility gap, correctly caught and closed

The first adapter cut re-exported `GLOBAL_SCOPE`/`PROJECT_SCOPE` and did not
expose `ProjectRegistry`/`project_registry_path` at all on `scripts.remember`.
`f95ce00` added direct imports of these from their true package homes
(`brain_eleven.memory`, `brain_eleven.projects.registry`) onto the adapter.
This matters because the codebase's test style monkeypatches
`module.ProjectRegistry` on the legacy module in several places — without
this fix, that pattern would silently patch a name the adapter didn't
re-export consistently. Caught by the implementer's own test suite before
this review, the same pattern as Slice 2C C3's `MemoryStore` identity fix.
Re-verified independently in a clean interpreter.

## Regression

- Focused suite (`test_memory_capture_package.py`, `test_remember.py`,
  `test_capture_safety.py`, `test_pre12_memory_state_caller_migration.py`):
  reproduced, **66 passed**.
- Full suite: reproduced, **936 passed, 2 warnings** — matches the report
  exactly.
- `flake8 --select=E9,F63,F7,F82` over CI's scope plus `brain_eleven/`: 0.
- `compileall` on `brain_eleven/memory` and both adapters: clean.
- Clean-interpreter identity check (package, adapter, bare `remember`,
  `remember_opt_in.py`'s `proactive_capture_policy`): all match.
- Working tree clean after sync.

## Safety / scope

- `install-cross-project-memory.py` (D2, archived per the C0 decision) is
  untouched — confirmed by diff.
- `capture_safety.py`, `memory-validator.py`, and `ProjectRegistry`'s own
  implementation are untouched — confirmed by diff. The B2.3 decision
  (minimal identity-preserving bridge, no logic copy) was followed exactly:
  `load_legacy_module("capture_safety", "capture_safety.py")` and the
  existing `MemoryValidator` bridge, no reimplementation.
- No new canonical write authority was introduced.

## P0 / P1 Findings

None.

## P2 Findings

None new.

## Final Verdict

**SHIP** — IG-07 Slice 2D Step D1 (`remember.py` → `brain_eleven/memory/capture.py`)
is accepted. This migration's core risk — a second canonical write path —
was verified absent both by reading the code and by a structural test that
would fail if one were ever introduced. Safety-check ordering and
concurrent-replay idempotence were proven under genuine conditions (a real
thread race, a registry that explodes if touched too early), not merely
asserted. `install-cross-project-memory.py` remains archived and untouched
per the C0 decision recorded in `IG07-SLICE2D-PLAN.md` §7. **Slice 2D is
now fully closed** (D1 shipped; D2 archived, out of scope). IG-07's
remaining scope is `task_model.py` (Slice 2E, per `IG07-SLICE2-PLAN.md`),
which requires its own new bounded plan; `task_state_context.py` stays
excluded pending a separate migration plan of its own.
