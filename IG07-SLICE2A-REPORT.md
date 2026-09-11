# IG-07 Slice 2A Package Report

**PACKAGE:** IG-07 Slice 2A
**REVISION:** `dff9d46` (implementation `1295c68`, tests `dff9d46`)
**OBJECTIVE:** Move the approved low-to-medium-risk runtime/support modules into
the `brain_eleven/` package while retaining legacy script compatibility and
without changing canonical authority or hook behavior.

## Scope completed

| Module | Canonical implementation | Implementation commit | Test commit | Canonical LOC (physical / nonblank) |
|---|---|---|---|---:|
| `memory_provenance.py` | `brain_eleven/memory/provenance.py` | `2d90c97` | `288f778` | 202 / 166 |
| `chat_interface.py` | `brain_eleven/runtime/chat_interface.py` | `72f66d9` | `ae63e82` | 424 / 360 |
| `post_session_maintenance.py` | `brain_eleven/runtime/maintenance.py` | `1295c68` | `dff9d46` | 166 / 132 |
| **Total** |  |  |  | **792 / 658** |

The three legacy scripts remain compatibility/direct-execution adapters. The
maintenance migration leaves `scripts/session_pipeline.py`'s subprocess path
and `--quiet` / `--generated-by-run` arguments unchanged. No hook budget was
expanded, no canonical write authority was added, and no next Slice 2A module
was started.

## Root causes addressed

- Production implementations for the three migrated surfaces now have an
  explicit package owner.
- Legacy imports and direct execution continue to resolve to the package
  implementation through thin adapters.
- The maintenance CLI retains best-effort failure isolation, atomic report
  writes, quiet output, and run lineage behavior.

## Tests added

- `tests/test_runtime_maintenance.py`: 4 tests covering package/legacy/bare
  object identity, adapter-only AST shape, report parity and canonical memory
  preservation, and hidden-window CLI behavior.
- The required existing maintenance tests (13) and session pipeline tests (4)
  were not modified.

## Tests executed

- Focused maintenance, pipeline, migration, and new adapter suite: **53 passed**.
- Required unchanged maintenance + pipeline tests: **17 passed**.
- Full repository regression: **895 passed, 2 warnings** in 164.28 seconds.
- Critical flake8 (`E9,F63,F7,F82`): **PASS**.
- `compileall` for the migrated package, adapter, and tests: **PASS**.
- Clean-interpreter package/legacy identity check: **PASS**.
- `git diff --check`: **PASS**.

## Quality and safety metrics

| Measure | Result |
|---|---|
| Package/legacy callable identity | PASS |
| Adapter contains duplicate implementation | PASS (no duplicate implementation) |
| Report parity | PASS after timestamp normalization in the test comparator |
| Canonical `validated-memory.json` mutation during maintenance | None observed |
| Hook budget / session pipeline command | Unchanged |
| Project or authority boundary changes | None |
| Remote CI evidence | Not run in this local implementation turn |

## Known limitations

- Independent read-only review is still required for this module and for the
  Slice 2A aggregate. Self-review is not graduation evidence.
- Remote CI evidence has not been claimed by this local report and must be
  supplied or explicitly bounded by the independent reviewer.

## Open failures

No local test, static check, parity check, or CLI smoke failure remains. The
independent review/acceptance gate remains open by design.

## Review and verdict

**INDEPENDENT REVIEW:** Pending. The reviewer must inspect the contract, all
three diffs, unchanged caller behavior, tests, and CI/runtime evidence.

**SCORE BEFORE / AFTER:** Not rescored in this implementation turn; Slice 2A
does not claim intelligence-quality improvement.

**VERDICT:** **REVIEW PENDING — NO SELF-SHIP**

The next module remains blocked until independent review accepts this slice.
