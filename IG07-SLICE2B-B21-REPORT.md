# IG-07 Slice 2B B2.1 — Knowledge Graph Projection

## PACKAGE

IG-07 Slice 2B, Step B2.1

## REVISION

Implementation revision: `63aa77d`  
Test revision: `080b089`  
This report is recorded in the follow-up documentation commit.

## OBJECTIVE

Invert the knowledge-graph projection bridge so that
`brain_eleven.graph.projection` is the canonical implementation. Preserve the
legacy `scripts.knowledge_graph` import/direct-execution surface and all
revision, persistence, corruption, source-availability, and scope semantics.

## FILES CHANGED

- `brain_eleven/graph/projection.py`: canonical `KnowledgeGraph` implementation,
  schema constant, projection exceptions, timestamp helper, persistence and
  query behavior.
- `scripts/knowledge_graph.py`: thin compatibility/direct-execution adapter
  with cached canonical loading, legacy exports, and bare-module alias support.
- `brain_eleven/extraction/__init__.py`: documentation-only clarification that
  entity extraction remains script-owned until B2.2; graph projection is now
  package-owned.
- `tests/test_graph_projection_package_migration.py`: ten migration/parity
  tests covering identity, adapter-only shape, persistence, status, source
  availability, scope isolation, and CLI compatibility.

Intentionally unchanged: `scripts/entity_extractor.py`, all entity extraction
implementation files, `brain_eleven/graph/__init__.py`, and canonical memory,
state, project, capture, retrieval, and Phase 20 paths.

## ROOT CAUSES ADDRESSED

- The package graph surface previously re-exported an implementation owned by
  `scripts/knowledge_graph.py`; ownership now points in the package direction.
- Canonical graph code no longer depends on `scripts.logging_config`.
- Legacy imports, object identity, bare-module compatibility, and the
  demonstration CLI remain available through one adapter path.

## TESTS ADDED

Ten tests in `tests/test_graph_projection_package_migration.py` (the malformed
and state-status cases are parametrized).

## TESTS EXECUTED

- Graph-focused regression set: **216 passed, 2 warnings**.
- Full test suite (`pytest tests -q`): **905 passed, 2 warnings**.
- Critical flake8 (`E9,F63,F7,F82`) on all touched Python files: **PASS**.
- `compileall` on all touched Python files: **PASS**.
- Four-surface object identity and canonical-dependency check: **PASS**.
- `git diff --check`: **PASS**.

## QUALITY METRICS BEFORE / AFTER

No retrieval or extraction quality claim is made by this structural migration.
Before, the package graph module was a bridge to the script implementation;
after, the package is the single implementation authority and the script is an
adapter. Existing graph behavior remained parity-tested.

## SAFETY METRICS

- Schema-2 `knowledge_graph` envelope and non-negative source revision checks:
  covered and passing.
- Fresh/stale/missing/legacy/corrupt/source-unavailable visibility:
  covered and passing.
- Backup-before-replace persistence behavior: covered and passing.
- Scope/project isolation: covered and passing.
- No new `MemoryStore` write path, authority, or locking/CAS bypass was added.

## KNOWN LIMITATIONS

- Independent read-only review has not yet been performed.
- B2.2 entity-extraction inversion has not started.
- Remote CI evidence is outside this local implementation report.

## OPEN FAILURES

No local test or static-check failures remain. The independent-review gate is
open and is required before this step can be accepted.

## INDEPENDENT REVIEW

**PENDING** — implementation self-review is not treated as independent.

## SCORE BEFORE / AFTER

Not scored as an intelligence-quality change. Architecture ownership and
compatibility evidence are recorded above; extraction, retrieval, correction,
and daily-use scores are unchanged.

## VERDICT

**REVIEW PENDING / NO SELF-SHIP**

