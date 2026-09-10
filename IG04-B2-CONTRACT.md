# IG-04-B2 — Review Queue Usability Contract

**Status:** APPROVED — HUMAN CHECKPOINT PASS (2026-09-10). Ahmet approved
this contract in the Claude session before implementation began.

**Package:** IG-04, Branch B, sub-package B2 (review queue usability)

**Implementation owner:** Codex.

**Program boundary:** Phase 20 remains FROZEN / LOCKED and V2 remains SHADOW.
This package does not reopen or change `IG04-B1-CONTRACT.md`'s boundary; it
extends the review surface B1 already built.

## Why this package exists

B1 made captured candidates safe (nothing reaches canonical memory without an
explicit accept), but it did not make the review queue *usable*. Today
`ReviewStore.list()` returns pending items in filename order — effectively
arbitrary — with no deduplication of near-identical candidates and no signal
for which item is worth Ahmet's attention first. A safety gate that's
tedious to operate gets ignored, and an ignored review queue means nothing
new ever becomes canonical — which defeats the product's actual purpose.
This is the highest-leverage next step for daily-use quality, not a new
retrieval-quality experiment.

## Current path and B2 boundary

```text
capture → queue → worker → ReviewStore.add() → PENDING
                                                   │
                                    B2 changes only this step:
                                                   ▼
                                    ReviewStore.list() ordering + dedup
                                                   │
                                                   ▼
                              existing /review UI/API, existing accept/reject
```

1. B2 changes only how pending candidates are **surfaced** — their ordering
   and deduplication in `ReviewStore.list()` and the `/api/review/candidates`
   response. It does not change accept, reject, expiry, canonical write, or
   any lifecycle status name defined in B1.
2. **Dedup:** when two or more `PENDING` candidates in the same project share
   the same content fingerprint (the fingerprint function B1 already built —
   see `ReviewStore.fingerprint`), only one is shown for review; the rest are
   recorded as duplicates of it (never silently deleted — their evidence
   references are preserved) and resolve together when the shown one is
   accepted or rejected.
3. **Ordering:** the queue is ordered by a deterministic, explainable
   priority — not a learned/tuned ranking model. A reasonable default:
   confidence (already on the candidate), age (older items surface before
   they expire), and candidate type. The exact formula must be written down
   in the implementation and covered by a test that asserts the order for a
   fixed input set — "looks about right" is not acceptable evidence.
4. B2 does not add embeddings, semantic similarity, or any model call to
   determine ordering or dedup. Both must be computable from data already on
   the candidate record.

The following remain unchanged from B1:

* Accept/reject/expire lifecycle and their tests;
* the canonical write path and its receipts;
* the `/review` UI/API's existing authentication and endpoints (B2 may add
  fields to existing responses, not new endpoints with a new authority);
* project scope enforcement — a project only ever sees its own queue.

## Acceptance criteria

B2 is complete only after the following evidence exists on one exact
revision:

1. **Dedup correctness:** two candidates with the same project + content
   fingerprint collapse to one review-visible item; accepting or rejecting it
   resolves both; a third, materially different candidate remains separately
   visible.
2. **Ordering is deterministic and tested:** a fixed set of candidates with
   known confidence/age/type produces the same, asserted order every run.
3. **No regression to B1:** all `test_ig04_b1_human_approval.py` cases still
   pass unmodified in behavior (dedup/ordering must not change what becomes
   canonical or when).
4. **No new leakage surface:** dedup/ordering must not merge or reorder
   across projects; a scoped listing test proves this explicitly for B2.
5. **Regression:** full existing suite stays green.
6. **Review:** an independent read-only reviewer (not the implementer)
   returns `SHIP`.

## Explicitly out of scope

* Any change to what makes a candidate `ACCEPTED`/`REJECTED`/`EXPIRED`, or to
  the canonical write path;
* embeddings, semantic similarity, or any model-scored ranking;
* a new storage format, new endpoint authority, or CLI beyond what B1 already
  exposes;
* V2 promotion, extraction/capture pipeline changes, or Phase 20 work of any
  kind.

## Required human checkpoint

Ahmet approved this contract on 2026-09-10, before implementation began, per
this project's standing rule (see `IG04-B1-CONTRACT.md`'s own checkpoint and
`CONTRIBUTING.md`'s roles section).
