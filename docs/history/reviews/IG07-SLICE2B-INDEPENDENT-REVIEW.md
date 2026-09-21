# IG-07 Slice 2B Combined Independent Review

**REVIEWED REPOSITORY:** `WinierKingYT/Brain-Eleven`
**REVIEWED BRANCH:** `master`
**REVIEWED HEAD:** `c8241a9` (B2.2: `351de87`, `143cb26`, `da8caed`, `38b9728`; combined report `c8241a9`)
**REVIEW DATE:** 2026-09-11
**REVIEWER:** Claude session `brain-eleven-66`
**REVIEWER ROLE:** Independent read-only reviewer
**IMPLEMENTATION PARTICIPATION:** None — implemented by Codex; this review
neither wrote nor edited `brain_eleven/extraction/entities.py`,
`brain_eleven/extraction/__init__.py`, `scripts/entity_extractor.py`,
`scripts/remember.py`, or their tests. B2.1 (graph projection) was already
independently reviewed and accepted separately (`IG07-SLICE2B-B21-INDEPENDENT-REVIEW.md`,
`SHIP`); this review covers B2.2 and closes the combined slice.

## Method

Independently re-run, not read-and-trusted:

- Diffed the moved implementation against the pre-migration script
  byte-for-byte, the same standard applied to B2.1.
- Read the full adapter (`scripts/entity_extractor.py`), the
  `brain_eleven/extraction/__init__.py` change, the `scripts/remember.py`
  caller-migration diff, and both new test files.
- Ran the plan's focused-suite list plus the new B2.2 tests, the full suite,
  CI's critical flake8 scope, `compileall`, a clean-interpreter identity
  check, and scope diffs against `brain_eleven/graph/*`, `scripts/knowledge_graph.py`,
  and canonical authority paths.

## Implementation move: exact-diff finding

`diff` between `scripts/entity_extractor.py` at the pre-B2.2 commit and the
new `brain_eleven/extraction/entities.py` shows **only**:
- the module docstring (updated to describe package ownership);
- an import reorder plus `Optional` added to the `typing` import (needed for
  the new `main(argv=...)` signature);
- one import line, `scripts.logging_config.setup_logging` →
  `brain_eleven.support.setup_logging`;
- the trailing CLI block wrapped into `main(argv: Optional[List[str]] = None) -> int`,
  called via `raise SystemExit(main())`, mirroring the same additive pattern
  used in B2.1's `projection.py` and Slice 2A's `maintenance.py`.

`TECH_LEXICON`, `PHASE_PATTERN`, `_slugify`, `ProjectionInvariantError`, and
the full `EntityExtractor` class (including `build_graph`) are byte-identical
in the new location. Same standard of evidence as B2.1: a genuine move, not a
rewrite claimed to be equivalent.

## Adapter and package-boundary shape

- `scripts/entity_extractor.py` follows the established `_load_canonical`
  pattern exactly (cache in `sys.modules`, re-export six names, preserve the
  bare-module alias and direct CLI). AST-walked independently: the only
  function defined is `_load_canonical`, no class definitions remain.
- `brain_eleven/extraction/__init__.py` now imports entity names from
  `.entities` instead of `scripts.entity_extractor`; the pre-existing
  `.semantic` exports are untouched. The inversion is complete on this side.
- `scripts/remember.py` was switched from a dynamic `_load_hyphenated_module`
  loader for `entity_extractor.py` to a plain `from brain_eleven.extraction
  import EntityExtractor`. Since that name is identity-bound through the
  adapter chain, this is a correct simplification, not a behavior change —
  and it removes one of the two legacy bridge/loader dependencies the plan
  flagged as needing inversion.

## Regression

- Focused suite (11 files: identity, migration, graph/scope/backup/chat/remember/search-api/post-session/pre12): reproduced, **203 passed, 2 warnings** — matches the report exactly.
- Full suite: reproduced, **913 passed, 2 warnings** — matches exactly.
- `flake8 --select=E9,F63,F7,F82` over CI's scope plus `brain_eleven/`: 0.
- `compileall` on `brain_eleven/extraction`, both adapters: clean.
- Clean-interpreter four-surface identity check (`brain_eleven.extraction`,
  `.entities`, `scripts.entity_extractor`, bare `entity_extractor`) for
  `EntityExtractor`, `ProjectionInvariantError`, `TECH_LEXICON`,
  `PHASE_PATTERN`: all identical objects.
- Working tree clean after sync; no stray or untracked files.

## Safety / scope

- `brain_eleven/graph/*` and `scripts/knowledge_graph.py` are untouched in
  this commit range — confirmed by diff, not by report claim; B2.1's closed
  work was not reopened.
- `MemoryStore`, `StateStore`, `ProjectRegistry`, `task_state_context.py`,
  and `brain_eleven/runtime/task.py` are untouched — confirmed by diff.
- Stale-revision rejection, eligible/ineligible memory filtering,
  technology/phase relationship deduplication, and project/global scope
  isolation are all covered by new tests and independently re-run green
  (`test_build_graph_rejects_stale_canonical_revision`,
  `test_build_graph_filters_ineligible_memories`,
  `test_extraction_keeps_technology_and_phase_relationships_deduplicated`,
  `test_project_graph_visibility_remains_isolated`).
- No new `MemoryStore` write path was introduced.

## P0 / P1 Findings

None.

## P2 Findings

None new. Slice 1's two open P2s (the `anomaly.py` `sys.modules` lookup
pattern; a hook-timing stabilization pass) remain open and unaffected.

## Final Verdict

**SHIP** — IG-07 Slice 2B is accepted in full (B2.1 graph projection +
B2.2 entity extraction). `brain_eleven/extraction/entities.py` and
`brain_eleven/graph/projection.py` are now the sole implementation
authorities for their respective surfaces; `scripts/entity_extractor.py` and
`scripts/knowledge_graph.py` are adapter-only with full object-identity and
behavioral parity across all four import surfaces (package, submodule,
script, bare). `scripts/remember.py` now consumes the package surface
directly. Canonical authority (`MemoryStore`/`StateStore`/`ProjectRegistry`),
capture/retrieval, `task_state_context.py`, and Phase 20 remain untouched
throughout. IG-07 Slice 2 as planned in `IG07-SLICE2-PLAN.md` is now fully
closed for sub-slice 2A and 2B; Slice 2C (`dedupe-validated-memory.py`,
`migrate-legacy-memory.py`, `migrate-memory-scope.py`) requires its own
bounded plan before implementation begins.
