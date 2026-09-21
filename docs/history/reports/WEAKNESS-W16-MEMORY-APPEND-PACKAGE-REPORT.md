# W-16 Canonical Memory Append Validation Package Report

**PACKAGE:** W-16
**REVISION:** `f831e3aa7c6c6c5d82f854c72ff99a99e3c0e601`
**STATUS:** CLOSED / SHIP — independently reviewed

## OBJECTIVE

Close the dormant `MemoryStore.append()` authority gap without changing the
canonical transaction implementation.  The public append boundary must reject
malformed nested records before any lock, revision, backup, or file effect,
while valid sparse and full legacy records retain their existing behavior.

## FILES CHANGED

- `scripts/memory_store.py`
- `brain_eleven/memory/store.py`
- `brain_eleven/memory/__init__.py`
- `tests/test_w16_memory_append_validation.py`
- `tests/test_memory_store.py` (three sparse fixture call sites made minimally valid)
- `tests/test_pre12_store_package_boundaries.py` (one sparse fixture call site made minimally valid)
- W-16 contract/test evidence commits preceding the implementation head

No `MemoryStore.transact()`, `replace()`, `append_validated()`,
`MemoryValidator`, `MemoryTruthEngine`, `StateStore`, `ProjectRegistry`,
retrieval, capture, V2, or Phase 20 implementation was changed.

## ROOT CAUSE ADDRESSED

`MemoryStore.append()` previously checked only the bucket and then persisted an
arbitrary dictionary through the canonical transaction path.  An isolated
probe confirmed that `{"memory_id": "malformed-only"}` reached revision 1 and
was returned by `load()`.  Production callers do not use this raw append
surface; the callers are fixtures/evaluation setup, so the bounded change is a
validation boundary rather than a production-writer migration.

## IMPLEMENTATION

`MemoryStoreRecordInvalid(MemoryStoreError)` and `_validate_record()` now run
before `append()` enters `transact()`.  The validator enforces non-empty
`memory_id`, `type`, and `content`; validates supplied optional field types,
scope/project metadata, approval and list fields; preserves unknown non-empty
lifecycle strings needed by existing negative fixtures; and permits unknown
extension fields.  The existing lock, reload, revision/CAS, backup, atomic
write, and transaction code is unchanged.  The new error is exported through
the package adapter so package and legacy surfaces retain identity.

## TESTS ADDED

`tests/test_w16_memory_append_validation.py` covers:

- non-mapping, missing, blank, and wrong-type required fields;
- invalid optional/lifecycle/scope/project fields with zero persistence effect;
- valid sparse/full record parity and package/legacy identity;
- stale expected-revision conflict preservation;
- global/project scope validity and project identity requirements.

The three authorized sparse fixture adjustments retain the existing fixture
intent and do not alter production behavior.

## TESTS EXECUTED

- W-16 append boundary plus existing caller/authority/lifecycle/graph/context
  surfaces: **170 passed, 2 warnings** after explicit-null coverage.
- Full suite at exact revision `f831e3a`: **1244 passed, 2 warnings** in
  244.49 seconds.
- Critical flake8 (`E9,F63,F7,F82`) on touched Python files: **PASS**.
- `compileall` on touched Python files: **PASS**.
- `git diff --check` on the current working tree: **PASS**. The historical
  `c6ec24c..HEAD` range contains only pre-existing Markdown line-break
  whitespace in earlier W-16 documents; no touched Python file is flagged.
  Pre-existing untracked permission warnings were not staged or modified.

## QUALITY METRICS BEFORE / AFTER

Before: malformed nested dictionaries could be committed by the public append
surface (confirmed by isolated revision/persistence probe).  After:
required-structure and supplied-field validation rejects malformed input before
the transaction; valid sparse/full records preserve values and revision/backup
parity.

## SAFETY METRICS

- Malformed rejection: zero canonical bytes, revision, or backup changes in
  focused tests.
- Stale expected revision: existing `MemoryStoreConflict` behavior remains
  visible with zero effect.
- Lock/CAS/revision/backup/atomic persistence path: unchanged and covered by
  existing regression tests.
- Package/legacy `MemoryStore` and invalid-error identity: preserved.
- Cross-project and retrieval/capture authorities: untouched.

## KNOWN LIMITATIONS

- No production `.append()` caller was found; this package hardens a dormant
  public authority surface and preserves fixture compatibility.
- Unknown non-empty lifecycle strings remain accepted for downstream lifecycle
  guards and existing `deleted`/`quarantined` negative fixtures.
- Unknown extension fields and intentionally omitted legacy optional fields are
  still allowed; this package does not introduce normalization or a new schema
  authority.
- Existing FastAPI/Starlette dependency deprecation warnings remain.

## OPEN FAILURES

No W-16 focused or full-suite failures remain at this head.  Independent
read-only review is still required; this report does not self-accept the
package.  W-07B and W-12A remain open, and W-17/W-18 remain queued.  Phase 20
is still `FROZEN / LOCKED` and V2 remains `SHADOW`.

## INDEPENDENT REVIEW

[`WEAKNESS-W16-MEMORY-APPEND-INDEPENDENT-REVIEW.md`](WEAKNESS-W16-MEMORY-APPEND-INDEPENDENT-REVIEW.md)
returned **SHIP** at exact review head
`3406d7b3d8863d687ea66b3112abc475363c4b30`.  The independent reviewer
verified explicit-null rejection, package identity, adapter boundary,
fixture scope, canonical transaction preservation, focused/full regression,
and critical static gates.

## SCORE BEFORE / AFTER

Persistence/concurrency: **8.0 → 8.0** (transaction/lock/CAS path preserved)
Scope/fail-closed safety: **8.0 → 8.2** (malformed append boundary closed)
Dormant append authority: **unvalidated nested records → bounded structural validation**

## VERDICT

**SHIP** — implementation, evidence, and independent review are pushed at
the exact review revision above.  Phase 20 remains `FROZEN / LOCKED` and V2
remains `SHADOW`.
