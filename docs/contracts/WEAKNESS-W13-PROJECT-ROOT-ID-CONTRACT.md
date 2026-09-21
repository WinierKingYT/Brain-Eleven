# W-13 Project Root / Project ID Consistency Contract

**Status:** REVIEW PENDING — implementation is not authorized by this document  
**Finding:** a supplied `project_root` and a supplied `project_id` can describe different projects.  
**Priority:** P1 scope/provenance isolation  
**Contract revision:** `27764ee2d12e609447e07ddcce459a5d333d0136` (audit baseline)

## Problem

`scripts/memory_scope.py::resolve_capture_scope()` accepts both a root and an
opaque project ID. When a root is supplied it obtains the registered identity,
but the current code only uses that identity when the caller's ID is empty:

```python
derived_id, derived_label = registered_project_identity(project_root, registry_path)
project_id = project_id or derived_id
project = project or derived_label
```

The caller's ID is therefore never compared with the root's registered ID.
`brain_eleven/memory/capture.py::remember()` passes both values through to this
resolver, and `scripts/search-api.py` passes both values from `MemoryCreate` to
`MemoryValidator.validate_single_and_append()`. A read-only reproduction at the
audit revision registered root A as `A-ID` and root B as `B-ID`; resolving root A
with `project_id="B-ID"` returned `("project", "a", "B-ID")`. The same pair
was accepted by `remember()` and by the `/memories` API, creating a record whose
label came from A while its namespace was B.

This violates the zero wrong-project-leakage invariant. `MemoryStore` locking
and transactions remain correct but cannot repair a semantically inconsistent
scope tuple after it has been accepted.

## Bounded objective

Make capture scope resolution fail closed whenever an explicitly supplied opaque
ID cannot be proven to belong to the supplied root. The fix belongs at the
scope-resolution boundary and must be shared by the package surface and all
callers. It must not add a second persistence authority or modify the canonical
store transaction.

### Allowed production scope

- `scripts/memory_scope.py::resolve_capture_scope()` and the package's existing
  re-export surface in `brain_eleven/memory/scope.py` only as needed to expose
  the same function/object.
- `brain_eleven/memory/capture.py` only if a stable, bounded error mapping is
  required for the existing `remember()` API.
- `scripts/search-api.py` only to map the resolver's bounded mismatch error to
  the existing validation response (expected HTTP 422), without introducing a
  second scope check.
- Focused tests and this package's evidence/report documents.

No change to `MemoryStore`, `ProjectRegistry`, `MemoryValidator` transaction
semantics, graph projection, retrieval ranking, V2 rollout, or Phase 20 is
authorized.

## Contracted behavior

1. **Root plus matching ID:** if the registry resolves `project_root` to the
   supplied `project_id`, resolution succeeds and returns the registry's opaque
   ID and label. The canonical record contains no absolute root path.
2. **Root plus different ID:** resolution fails closed with one documented,
   deterministic scope error (recommended code/message:
   `PROJECT_ROOT_ID_MISMATCH`). No `MemoryStore`, graph, or registry write is
   allowed as a consequence of the rejected capture. The API maps this to its
   existing 422 validation shape.
3. **Unregistered root plus explicit ID:** do not silently generate a second
   identity and accept the pair. The bounded default is to reject with
   `PROJECT_ROOT_ID_UNREGISTERED` unless the existing registration API is
   explicitly invoked before capture. Root-only calls retain their current
   auto-registration behavior and opaque-ID continuity.
4. **Root only:** preserve current `registered_project_identity()` behavior,
   including relocation stability and the existing label derivation.
5. **Explicit ID without root:** preserve existing legacy behavior where scope
   is project and the caller supplies the namespace. This path has no root
   claim to validate.
6. **Global scope:** continue rejecting project labels and project IDs. A root
   alone remains ignored for explicit global captures because the CLI supplies
   its working root by default; this existing behavior is unchanged. A root
   plus an explicit project ID still rejects via the global metadata check.
7. **Safety ordering:** `capture_safety.evaluate_capture()` remains before
   registry resolution and persistence. A rejected secret or malformed capture
   produces no registry, memory, or graph effect.
8. **Isolation:** a rejected A-root/B-ID request must not become visible under
   B, and equal content from two valid project roots remains independently
   namespaced.

The implementation may choose an equivalent typed exception instead of the
recommended string code, but the error identity and API mapping must be stable
and documented. It must not catch a mismatch and fall back to the caller's ID.

## Evidence and tests

### Before implementation

- Record exact `git rev-parse HEAD`.
- Reproduce root A + `A-ID`, root A + `B-ID`, root-only, explicit-ID-only and
  global cases directly through `resolve_capture_scope()`.
- Reproduce the mismatch through `remember()` and `/memories`; record that the
  current behavior returns success and writes a mixed record.

### Focused regression

Add tests without weakening existing tests:

- `resolve_capture_scope(root_a, project_id=B_ID)` rejects with the documented
  mismatch and leaves registry revision, memory revision, and graph unchanged.
- Matching root/ID succeeds and uses the registry label/ID.
- Unregistered root plus explicit ID rejects without auto-registration or
  canonical writes; root-only still auto-registers.
- Root relocation preserves its opaque ID and accepts that ID after relocation.
- `remember()` rejects before `MemoryValidator`/graph effects on mismatch.
- `/memories` returns the existing 422 validation response for mismatch.
- A valid A capture is never returned by a B project search; two valid roots
  with identical content remain separate.
- Global scope continues to reject project metadata.
- Existing safety rejection ordering remains intact.

### Verification gates

1. **Identity/surface:** package and legacy scope surfaces refer to the same
   resolver and error object; no second scope implementation is introduced.
2. **Boundary/static:** AST/source audit confirms no direct file write, graph
   write, or MemoryStore mutation was added to the resolver.
3. **Parity and safety:** existing scope, capture, API, registry relocation,
   graph-isolation, and pre-12 caller-migration tests pass unchanged, plus the
   new mismatch cases.
4. **Full verification:** full `pytest tests -q`, critical flake8 (`E9,F63,F7,F82`),
   compile/import sanity, and `git diff --check` at one exact revision.
5. **Independent review:** a read-only reviewer checks the diff, exact evidence,
   no wrong-project leakage, no hidden registration side effect, and confirms
   `SHIP`, `FIX-FIRST`, or `RETHINK`. Self-review is not acceptance.

## Explicit non-goals

- No retrieval or ranking changes.
- No change to proactive opt-in policy; manual `remember()` remains explicit.
- No rewrite of `ProjectRegistry` or `MemoryValidator`.
- No migration of `memory_scope.py` into a new package in this finding.
- No automatic repair or reclassification of records already written with a
  mixed root/ID tuple; any remediation requires a separate bounded package.
- No V2 promotion, Phase 20 work, or unrelated cleanup.

## Package report template

```text
PACKAGE: W-13
REVISION: <exact implementation SHA>
OBJECTIVE: Reject inconsistent project_root/project_id pairs at scope boundary.
FILES CHANGED: ...
ROOT CAUSE ADDRESSED: ...
TESTS ADDED: ...
TESTS EXECUTED: ...
QUALITY METRICS BEFORE: ...
QUALITY METRICS AFTER: ...
SAFETY METRICS: wrong-project leakage, rejected side effects, registry revisions
KNOWN LIMITATIONS: ...
OPEN FAILURES: ...
INDEPENDENT REVIEW: SHIP / FIX-FIRST / RETHINK
SCORE BEFORE: ...
SCORE AFTER: ...
VERDICT: REVIEW PENDING
```

**Implementation authorization:** not granted until this contract receives an
independent read-only contract review. Phase 20 remains `FROZEN / LOCKED` and
V2 remains `SHADOW`.

