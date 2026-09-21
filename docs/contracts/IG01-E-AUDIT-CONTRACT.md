# IG01-E Independent Evaluation Audit Contract

**Status:** CURRENT / BOUNDED CONTRACT  
**Package:** IG01-E  
**Purpose:** independently audit the IG01 measurement foundation before IG-01
is closed.

IG01-E is read-only with respect to product behavior. It may open the public
HOLDOUT only inside a sealed integrity check that returns counts and hashes.
It must never tune a provider, change labels, write MemoryStore/StateStore or
emit prompt, transcript, memory or secret content.

## Audit invariants

The audit must prove all of the following on one exact repository revision:

1. Phase 20 is explicitly `FROZEN / LOCKED` and V2 is `SHADOW`.
2. IG01-A through IG01-D contracts and reports are present and classified by
   `DOCUMENTATION-AUTHORITY.md`; IG01-D has a user checkpoint `PASS`.
3. The public `ig-eval-v2` corpus has its required 17-phenomenon × 3-language
   matrix, immutable holdout sidecar/manifest/tag hash, distinct splits and
   zero privacy hits.
4. Private realistic data is local-only and no private candidate is tracked or
   present under public/failure corpus paths.
5. The evaluator is offline, production-independent and cannot write canonical
   authorities. Its report remains content-free.
6. Anti-gaming controls measure both select-all and select-none, and hard
   safety gates remain individually visible.
7. IG01-D V1/V2 evidence binds both providers to identical corpus/source
   identities, uses public DEV+TEST only, and records semantic unavailability
   explicitly without fabricating a score.
8. The remote IG01-D pair artifact is downloaded from the same workflow run and
   strict-validated against the current `github.sha`; the historical report is
   never used as a substitute for that artifact.

## Evidence contract

`evals.ig01e.audit.audit_repository()` emits only revision, paths, hashes,
counts, bounded statuses and boolean gate results. It does not persist corpus
rows. A `SHIP` result requires every check to pass. A missing input, changed
holdout, privacy hit, tracked private file, production/network import,
missing anti-gaming control or undocumented package boundary is `FIX-FIRST`.

The audit report is immutable evidence for the exact `git rev-parse HEAD` that
produced it. A later source, corpus, evaluator or label change requires a new
audit report and a new IG01-E revision/tag; reports are never silently
re-baselined.

The repository has older Phase-15 workflows that intentionally evaluate their
own historical holdout suites. Those jobs are outside IG01-D’s public baseline
scope. IG01-E records this scope explicitly; it does not treat those historical
quality runs as evidence that the IG01-B holdout was used for tuning.

## Scope and stop point

This package does not implement semantic extraction, correction resolution,
task-aware retrieval, capture closure, V2 promotion, architecture rewrites or
Phase 20 work. Even after an IG01-E technical `SHIP`, IG-01 remains open until
the user completes the IG-01 closure human checkpoint (20 random corpus labels
and the complete IG01-C diff review). Only then may the next explicitly
authorized intelligence package begin.
