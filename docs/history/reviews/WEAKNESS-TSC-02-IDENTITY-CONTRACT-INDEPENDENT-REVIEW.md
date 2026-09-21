# TSC-02 — Independent Contract Review

**Contract revision reviewed:** `62dfedf`
**Reviewed predecessor:** `e87afd8`
**Review type:** independent, read-only contract review
**Implementation reviewed:** none
**Verdict:** `SHIP`

## Review scope

This review covers only `WEAKNESS-TSC-02-IDENTITY-CONTRACT.md` at the exact
revision above. The review checked the bounded production surface against the
current task/state, ProjectRegistry, Router, Authority and serialization
boundaries, and checked that the revised contract resolves the blockers found
against the initial `e87afd8` wording.

## Findings

### Compatibility and privacy boundary — PASS

The revised contract explicitly retains the historical
`TaskEnvelope.request.raw` field and limits the new privacy requirement to
lineage fields, lineage errors and lineage telemetry. This is compatible with
the existing `TaskEnvelope.to_dict()` contract and its raw-request round-trip
tests. The contract also keeps non-lineage registry/state error text outside
this package and requires a separate privacy contract if that text must be
redesigned. This removes the previous parity/privacy contradiction without
silently weakening the new lineage guarantee.

### Unresolved and global lineage — PASS

The revised schema policy gives unresolved contexts the explicit
`{"status": "unresolved"}` lineage form and global-only routes the explicit
`{"status": "global"}` form. It also states that neither form may be promoted
to a current-project route by a caller-supplied project ID. The required
project-candidate prohibition is therefore observable and testable rather than
being inferred from a missing field.

### Registry snapshot and race policy — PASS

Using the existing `ProjectRegistry.load()` snapshot is feasible without
changing registry persistence. The accepted two-phase policy is concrete:
resolve/read, re-read before publishing, and compare project ID, normalized
root and non-negative revision. Relocation and root reuse therefore have
distinct, testable outcomes while stable project IDs remain intact.

### Router and Authority cache ordering — PASS

The contract requires lineage validation before RouterCache/AuthorityCache
lookups and requires stale lineage never to be returned as a successful or
degraded current-project result. Existing cache interfaces compare opaque
revision mappings, so the implementer can carry registry revision metadata or
perform the required final revalidation within the bounded Router/Authority
surfaces without changing cache persistence. The implementation review must
verify the race window around cache lookup, as required by the contract's
registry-race invariant.

### Serialization and evaluation boundary — PASS

The contract uses an explicit new TaskStateContext schema version, strict
lineage shapes, and an explicit schema-1 policy. It correctly records that the
current tree has no dedicated `tests/test_authority_serialization.py`; new
focused lineage/serialization tests are required instead. `evals/task_state_eval.py`
and frozen holdout labels/cases remain read-only, so the contract does not
permit evaluation goalpost changes.

### Scope and authority — PASS

The package is bounded to context composition, one read-only identity utility,
Router/Authority validation, serialization and focused evidence. It excludes
ProjectRegistry persistence, MemoryStore/StateStore writes, retrieval,
capture, V2 promotion, task-state package inversion and Phase 20. No second
canonical authority or repair write path is authorized.

## Implementation acceptance conditions

These are verification obligations, not contract blockers:

- prove that a registry mutation between lineage validation and cache use is
  detected or cannot yield a stale cache hit;
- exercise both explicit unresolved and global-only forms, including the
  prohibition on later promotion to a project route;
- prove all new lineage errors and telemetry are path/content-free while
  preserving the historical raw-request field;
- compare the frozen task-state evaluation inputs and labels without changing
  them.

## Decision

`SHIP` — the revised TSC-02 contract is bounded, internally coherent and
implementable against the current repository surfaces. This verdict accepts
the contract for implementation only; it does not accept an implementation or
replace the required independent implementation review.

