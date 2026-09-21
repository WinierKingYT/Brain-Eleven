# IG-07 Slice 2B Step B2.1 Independent Review

**REVIEWED REPOSITORY:** `WinierKingYT/Brain-Eleven`
**REVIEWED BRANCH:** `master`
**REVIEWED HEAD:** `1f16b2a` (implementation `63aa77d`, tests `080b089`, report `50489b1`)
**REVIEW DATE:** 2026-09-11
**REVIEWER:** Claude session `brain-eleven-66`
**REVIEWER ROLE:** Independent read-only reviewer
**IMPLEMENTATION PARTICIPATION:** None — implemented by Codex; this review
neither wrote nor edited `brain_eleven/graph/projection.py`,
`scripts/knowledge_graph.py`, `brain_eleven/extraction/__init__.py`, or their
tests.

## Method

Independently re-run, not read-and-trusted:

- Diffed the moved implementation against the pre-migration script
  byte-for-byte (`diff` on the two full files) to confirm the move carried no
  hidden behavior change, not just a report claim.
- Read the full adapter (`scripts/knowledge_graph.py`) and the new test file
  (`tests/test_graph_projection_package_migration.py`).
- Ran the plan's exact focused-suite list (10 files) plus the new migration
  tests, the full suite, CI's critical flake8 scope, `compileall`, a
  clean-interpreter identity check, and `git diff --check`.
- Diffed the commit range against `scripts/entity_extractor.py`,
  `brain_eleven/graph/__init__.py`, and all canonical memory/authority paths
  to confirm the "intentionally unchanged" claim.

## Implementation move: exact-diff finding

`diff` between `scripts/knowledge_graph.py` at the parent commit and the new
`brain_eleven/graph/projection.py` shows **only**:
- the module docstring (updated to describe the new ownership direction);
- one import line, `scripts.logging_config.setup_logging` →
  `brain_eleven.support.setup_logging`;
- the trailing `if __name__ == "__main__":` block wrapped into a `main()`
  function returning `0`, called via `raise SystemExit(main())`.

Every class, method, constant, and the persistence/query/scope logic between
lines 35–384 of the original file are byte-identical in the new location.
This is a genuine move, not a rewrite-with-claimed-parity — the strongest
form of evidence for this kind of migration.

## Adapter shape

`scripts/knowledge_graph.py` follows the same `_load_canonical` pattern used
in Slice 1 and Slice 2A: caches the canonical module in `sys.modules`,
re-exports the four public names plus `_utc_now`, `main`, and `logger`,
preserves the historical bare-module alias, and keeps the direct-execution
CLI. AST-walked independently: the only function defined in the script is
`_load_canonical`; no class definitions remain. Confirmed by direct
inspection, not just by the new test asserting it.

## Regression

- Plan's 10-file focused suite + new migration tests: reproduced, **216
  passed, 2 warnings** — matches the report exactly.
- Full suite: reproduced, **905 passed, 2 warnings** — matches exactly.
- `flake8 --select=E9,F63,F7,F82` over CI's scope plus `brain_eleven/`: 0.
- `compileall` on all touched paths: clean.
- Clean-interpreter four-surface identity check
  (`brain_eleven.graph`, `.projection`, `scripts.knowledge_graph`, bare
  `knowledge_graph`): all three classes and the schema constant match.
- `git diff --check` flags two trailing-whitespace lines and a final blank
  line in `IG07-SLICE2B-B21-REPORT.md` — these are intentional Markdown
  hard-line-breaks (two trailing spaces), the same convention already used
  in `IG07-SLICE1-REPORT.md`. Not a defect; noted only for completeness.

## Safety / scope

- `scripts/entity_extractor.py`, `brain_eleven/graph/__init__.py`, and every
  canonical `MemoryStore`/`StateStore`/`ProjectRegistry` path are untouched
  in this commit range — confirmed by diff, not by report claim.
- `brain_eleven/extraction/__init__.py`'s only change is a docstring
  clarifying that entity extraction remains script-owned until B2.2; no code
  changed there.
- No new `MemoryStore` write path, authority, or locking/CAS bypass was
  added — the new module still only reads `MemoryStore(...).revision()`.
- Revision, lock, corruption, and scope invariants specified in
  `IG07-SLICE2B-PLAN.md` section 4 are all covered by the new parametrized
  test (`missing`/`legacy`/`malformed`/`invalid-envelope` → correct states)
  and the `source_unavailable` mapping test.

## P0 / P1 Findings

None.

## P2 Findings

None new. Slice 1's two open P2s (the `anomaly.py` `sys.modules` lookup
pattern; a hook-timing stabilization pass) remain open and unaffected.

## Final Verdict

**SHIP** — IG-07 Slice 2B Step B2.1 (knowledge-graph projection inversion)
is accepted. `brain_eleven.graph.projection` is now the sole implementation;
`scripts/knowledge_graph.py` is adapter-only with full object-identity and
behavioral parity. Step B2.2 (entity extraction inversion into
`brain_eleven/extraction/entities.py`) may now begin, per
`IG07-SLICE2B-PLAN.md` section 2's dependency order — entity extraction can
safely consume the now-canonical graph surface. Slice 2B as a whole remains
open until B2.2 is implemented and independently reviewed.
