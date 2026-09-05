# Context Engine Foundation V1 — Freeze Record

**Status:** `FREEZE READY` — the immutable `context-engine-foundation-v1` tag
is created only after this documentation revision completes a successful full
Validation workflow. At that point the tag, the reviewed code, and the
revision-bound evidence form the frozen Foundation V1 record.

Reviewed implementation evidence:

- Code review SHA: `8f5513129d369525d3ffca1090cbd561323e0cfa`
- Full Validation: [run #55](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33968422634) — **success**
- Independent read-only review: [`CONTEXT-ENGINE-FOUNDATION-V1-INDEPENDENT-REVIEW.md`](CONTEXT-ENGINE-FOUNDATION-V1-INDEPENDENT-REVIEW.md) — **SHIP**

## Foundation boundary

Context Engine Foundation V1 is the stable contract spanning:

| Phase | Component | Runtime policy |
|---|---|---|
| 15 | Offline Evaluation Harness | Measurement authority; synthetic public corpus only |
| 16 | Task + State Model | Canonical current-state authority, separate from memory |
| 17 | Task-Aware Context Router | `OFF` / `SHADOW` only |
| 18 | Metadata-First Authority Resolver | `OFF` / `SHADOW` only |
| 19 | Context Compiler V2 + Token Budgeter | `OFF` / `SHADOW` only; V1 remains active |

Phase 20+ code must not silently alter these contracts. A behaviour change
requires a new policy/contract version and rerun evidence; a schema change
requires a new migration contract.

## Locked authorities

- `MemoryStore` remains canonical durable history.
- `ProjectRegistry` remains canonical project identity and lifecycle.
- `StateStore` remains canonical mutable project truth.
- `TaskEnvelope` is a runtime task description, not durable state.
- Router, Authority and Compiler V2 are read-only derived consumers. They
  must never write canonical memory, registry or state.

## Safety invariants

- Default scope is current project plus explicit global records only.
- Raw task text cannot widen trusted project, history, archived, or rollout
  permissions.
- Corrupt canonical input is a failure, never an empty success.
- Stale input is rejected; graph/cache artifacts are derived and disposable.
- State mutations are typed, provenance-carrying, revisioned, locked and
  atomic. Lost updates are not acceptable.
- Authority uses explicit metadata only. Retrieval score and free prose never
  manufacture a winner.
- Mandatory compiler context is preserved or reported as
  `INSUFFICIENT_BUDGET`; it is never silently truncated.
- Secrets and renderer delimiters cannot become model-facing context or
  content-free telemetry/cache data.

## Evidence contract

The master-only `Context Engine Foundation V1 graduation` workflow produces
`.phase-evidence/context-engine-foundation-v1.json` only after Phase 15–19
evidence artifacts and the cross-phase graduation suite pass on the same Git
revision. It records hard-invariant values and intentionally records
`PENDING_INDEPENDENT_REVIEW` rather than inventing a review verdict.

Required final checks are:

1. Ubuntu and Windows unit jobs are green for the candidate SHA.
2. Integration, security, coverage and full public/holdout evaluations are
   green.
3. The five phase manifests and foundation manifest are revision-bound to the
   candidate SHA.
4. An independent read-only Foundation review returns `SHIP` for the complete
   Phase 15–19 cross-phase chain.
5. This document, `PROJECT-STATUS.md`, evidence and the immutable release tag
   bind to the same final documentation revision.

## Known limits at candidate time

- The V2 compiler is deliberately not promoted into SessionStart. Its current
  relevance/recall is a shadow diagnostic and may be lower than V1 while its
  safety gates remain green.
- Phase 18 is metadata-first. It abstains from semantic contradictions that
  do not have explicit canonical lifecycle/provenance metadata.
- Performance measurements are informational p50/p95 values at 100, 1,000
  and 10,000-memory scales; there is no absolute latency gate in V1.

## Freeze change policy

- **Patch:** non-breaking bug, security or compatibility fix; add regression
  test and regenerate evidence.
- **Minor:** observable policy behaviour change; publish a new foundation
  minor version and compare against the frozen corpus.
- **Major:** schema or authority-boundary change; create a new phase and
  migration contract instead of changing V1 silently.
