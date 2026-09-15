# W-16 Canonical Memory Append Validation Contract

**Status:** REVIEW PENDING — implementation is not authorized by this document  
**Finding:** public `MemoryStore.append()` validates only the bucket name and
can persist an arbitrary nested dictionary as canonical memory.  
**Priority:** P2 dormant authority surface  
**Contract revision:** `c6ec24c` (W-15 close baseline)

## Evidence

At `scripts/memory_store.py:197-212`, `MemoryStore.append()` checks that the
bucket is `validated_memory` or `rejected_memory`, then appends
`dict(record)` inside the existing lock/reload/revision/atomic transaction.
`_normalize()` validates only the outer document and bucket lists; it does not
validate nested records.

An isolated temporary-vault probe successfully executed
`MemoryStore(vault).append({"memory_id": "malformed-only"})`.  Revision 1 was
written and a later `load()` returned the malformed record unchanged.  The
package and legacy surfaces are the same `MemoryStore` authority
(`brain_eleven/memory/store.py` and `scripts/memory_store.py`).  No production
caller of `.append()` was found; callers are fixtures/evaluation setup.  The
canonical production paths use `MemoryValidator`/truth transactions instead.

## Bounded objective

Keep the existing lock, CAS/revision, backup and atomic persistence behavior,
but prevent the public append surface from creating records that downstream
canonical readers cannot safely interpret.  Preserve valid legacy fixture
records and the package/legacy object identity contract.

The preferred narrow boundary is a structural validator invoked by `append()`:

- `record` must be a mapping with non-empty string `memory_id`, `type`, and
  `content` fields;
- if present, `status` must be a non-empty string.  Known lifecycle values are
  preserved, while unknown string values remain readable for downstream
  lifecycle guards to classify (for example, `deleted` and `quarantined` are
  intentional negative fixtures);
- if present, `scope` must be `global` or `project`; project scope requires a
  non-empty `project_id`, while global scope rejects non-empty project
  metadata.  If `scope` is omitted for a legacy record, it is treated as
  legacy-global for this validation, so a non-empty `project_id` or project
  label is rejected rather than silently reclassified;
- if present, `timestamp`, `source_id`, `source`, `dedup_fingerprint`,
  `project`, and `project_label` must be strings; `is_approved` must be a
  boolean; nested `issues` and `related_notes` must be lists;
- unknown extension fields remain allowed for forward compatibility, but no
  field may replace the required identity/content/type boundary.

This keeps sparse historical records usable while rejecting malformed records
and validating scope/lifecycle fields whenever they are supplied.  No record
normalization, automatic defaulting, or new authority is introduced.

## Allowed scope

- `scripts/memory_store.py`: private record validator and its call from
  `MemoryStore.append()`; existing transaction code must remain unchanged.
- Only the package adapter/export if required to expose validator error
  identity (no duplicate `MemoryStore`).
- Focused tests and evidence/package documents.  Two sparse fixture records may
  be made minimally valid by adding `content`; specifically the two call sites
  in `tests/test_memory_store.py` (the normal append and stale-conflict setup)
  and the one call site in `tests/test_pre12_store_package_boundaries.py` are
  the complete fixture adjustment scope.  No production caller migration is
  expected.

`MemoryStore.transact()`, `replace()`, `append_validated()`,
`MemoryValidator`, `MemoryTruthEngine`, `StateStore`, `ProjectRegistry`,
retrieval, V2, capture flow, and Phase 20 are out of scope.

## Required semantics

1. **Malformed rejection:** non-mapping records, missing/blank required fields,
   invalid field types, blank lifecycle values and invalid scope metadata
   raise a stable `MemoryStoreRecordInvalid(MemoryStoreError)` exception before
   the transaction starts.  Revision, backup and canonical data remain
   unchanged.
2. **Valid parity:** records already accepted by current tests and canonical
   validator/truth paths append with identical field values, revision changes,
   backup creation and expected-revision conflict behavior.
3. **Scope safety:** global records cannot carry a non-empty project identity;
   project records cannot omit `project_id`.  No path or registry inference is
   added to `append()`.
4. **Lifecycle safety:** supplied status values must be explicit non-empty
   strings; unknown string statuses remain available for downstream guard
   classification.  Absent optional legacy fields remain absent rather than
   being silently invented.  Required string fields and `project_id` are
   rejected when empty after whitespace stripping; valid stored values retain
   their original bytes/field values.
5. **Authority boundary:** all accepted writes still pass through the existing
   `transact()` lock/CAS/atomic path.  No direct file write or second store is
   allowed.
6. **Compatibility:** package, legacy and bare-module `MemoryStore` identity
   remains unchanged; `append()` bucket and return shape remain unchanged for
   valid records.

## Test and evidence plan

### Baseline and reproduction

- Record exact `git rev-parse HEAD`.
- Re-run the malformed-only append probe as the visible pre-fix red baseline.
- Inventory `.append()` callers and confirm production caller count remains
  zero; update only sparse fixture inputs needed by the new minimum boundary.

### Focused tests

- `{}`, missing `memory_id`, missing `type`, missing `content`, blank values,
  non-string required values: reject with no revision/backup/effect;
- invalid `status`, invalid `scope`, global project metadata, project scope
  without identity and invalid optional field types: reject;
- valid sparse legacy and fully populated canonical records: append parity;
- expected-revision stale writer still raises `MemoryStoreConflict`;
- backup, concurrent writers, corrupt envelope and package/legacy identity
  tests remain unchanged;
- direct test/eval fixture callers continue to work after minimal fixture
  completion.

### Verification gates

1. **Boundary proof:** AST/source review shows validation occurs before
   `transact()` and no direct write or duplicate authority was added.
2. **Safety proof:** every malformed case leaves bytes, revision, ID set and
   backup state unchanged.
3. **Parity:** existing memory-store, graph, context, migration, lifecycle,
   state-reference and package-boundary tests pass unchanged except for the
   two minimally completed fixtures.
4. **Full verification:** full `pytest tests -q`, critical flake8
   (`E9,F63,F7,F82`), compileall and `git diff --check` at one exact revision.
5. **Independent review:** a read-only reviewer checks validator completeness,
   legacy compatibility, lock/CAS preservation, caller scope and exact
   revision, then returns only `SHIP`, `FIX-FIRST`, or `RETHINK`.

## Explicit non-goals

- No full `ValidatedMemory` schema migration or automatic field defaulting.
- No change to production capture/truth validation or nested-record repair.
- No removal of the `append()` API in this package; a future deprecation or
  private-only decision would require a separate contract.
- No retrieval, context, V2, Phase 20 or unrelated persistence work.

## Package report template

```text
PACKAGE: W-16
REVISION: <exact implementation SHA>
OBJECTIVE: Reject malformed nested records at MemoryStore.append().
FILES CHANGED: ...
ROOT CAUSE ADDRESSED: ...
TESTS ADDED: ...
TESTS EXECUTED: ...
QUALITY METRICS BEFORE: malformed append persisted / ...
QUALITY METRICS AFTER: ...
SAFETY METRICS: zero malformed effects, valid parity, conflict preservation
KNOWN LIMITATIONS: ...
OPEN FAILURES: ...
INDEPENDENT REVIEW: SHIP / FIX-FIRST / RETHINK
SCORE BEFORE: ...
SCORE AFTER: ...
VERDICT: REVIEW PENDING
```

**Implementation authorization:** not granted until independent contract
review.  Phase 20 remains `FROZEN / LOCKED`; V2 remains `SHADOW`.
