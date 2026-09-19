# IG-07 Slice 2F — Package Report

**PACKAGE:** IG-07 / Slice 2F
**REVISION:** Working tree based on `HEAD ea4276dc74a2c5c1de364822efaf0072cfe9c385`;
the slice is not committed.
**OBJECTIVE:** Invert `task_state_context.py` so the runtime package owns one
task/state/lineage composition implementation while legacy imports and direct
CLI execution remain compatible.

## Files and scope

- Canonical implementation: `brain_eleven/runtime/task_state_context.py`.
- Thin compatibility/direct-execution adapter: `scripts/task_state_context.py`.
- 14 production/evaluation import edges moved to
  `brain_eleven.runtime.task_state_context`; 12 behavioral test callers keep
  the historical bare import for compatibility coverage.
- Coverage and source-fingerprint allowlists now measure the canonical package
  path, not only the legacy adapter.
- Added `tests/test_task_state_context_package_migration.py` and adjusted the
  prior migration/coverage tests for the Slice 2F boundary.

The 26-file AST inventory is recorded in `IG07-SLICE2F-PLAN.md`. The canonical
top-level class/function definition AST is equal to the pre-inversion
`HEAD:scripts/task_state_context.py` implementation; only ownership,
dependency imports and adapter behavior changed.

## Contract and safety evidence

- Schema remains version 1 with ordered envelope keys
  `schema_version`, `task`, `state`, `lineage`.
- Resolved, unresolved and global lineage rules remain explicit and
  project-safe; registry changes between reads remain fail-closed.
- Task model, state resolver and project registry remain separate authorities.
- Canonical source has no `MemoryStore`/`StateStore` writer, JSON/file write,
  registration or transaction path; the adapter has no duplicate class,
  function, dataclass, persistence or CLI implementation.
- Package, `scripts.task_state_context` and bare `task_state_context` public
  objects are identical. Canonical class ownership is
  `brain_eleven.runtime.task_state_context`.
- Valid, archived and unresolved fixtures match across all three import
  surfaces. Adapter/package JSON and human CLI output match after removing
  generated task ID and timestamp. Corrupt registry CLI output returns the
  bounded `TASK_STATE_ERROR` contract without path or request leakage.
- Existing task/state smoke, public and holdout evaluator JSON reports remain
  equal to their immutable Slice 2E baselines.

## Verification

| Check | Result |
|---|---|
| Slice 2F focused and boundary suite | **143 passed** |
| Full baseline: `tests/ -m "not integration and not graduation"`, W06C0R1 ignored | **1359 passed, 4 skipped, 82 deselected** |
| `python -m compileall -q brain_eleven scripts tests/test_task_state_context_package_migration.py` | **passed** |
| Focused `flake8` E9/F63/F7/F82 gate | **passed** |
| `git diff --check` | **passed**; only existing LF/CRLF normalization warnings |
| Production direct `scripts.task_state_context` imports | **none**; the only remaining hit is the intentional identity test |
| Pre-inversion top-level definition AST comparison | **equal** |

**INDEPENDENT REVIEW:** Not separately commissioned in this six-work goal;
the automated package, parity, fail-closed and regression gates above are the
recorded acceptance evidence.
**OPEN FAILURES:** None in the executed scope.
**VERDICT:** COMPLETE FOR THE BOUNDED SLICE.
