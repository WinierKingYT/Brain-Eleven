# IG01-F Contract and Pre-registration — Recency Continuity

**Status:** FROZEN BEFORE MEASUREMENT

**Provider:** `recency_continuity`

**Corpus:** a new, generated `ig01f-recency-v1` DEV/VALIDATION projection of
`ig-eval-v2`; the existing `ig-eval-v2` files, labels, and HOLDOUT remain
immutable and are never opened by the generator or runner.

## Owner resolution after Phase 0

The owner authorized preparation of the missing time-aware canonical-store
projection after the Phase 0 STOP. IG01-F therefore creates a separate derived
corpus rather than modifying IG01-D or `ig-eval-v2`.

All three arms are re-measured in the IG01-F harness at one common budget:

- maximum context: 2048 conservative tokens;
- minimum headroom: 128 tokens (1920 usable);
- hard rendered UTF-8 limit: 24,000 bytes;
- estimator: `utf8-conservative-v1`, `ceil(utf8_bytes / 3) + 1`.

Preserved IG01-D evidence is not rewritten. The IG01-F harness adapts V1, V2,
and recency outputs to the same rendered-size budget before scoring.

## Frozen derived-corpus rules

Only `dev.jsonl`, `validation.jsonl`, `abstention.jsonl`, and `manifest.json`
from `ig-eval-v2` may be opened. Any path containing `holdout` is rejected
before filesystem access.

Each public case becomes one isolated synthetic canonical vault. Candidate IDs,
required/acceptable/mandatory/forbidden labels, project identity, category,
language, and provenance event time are preserved. Candidate content is
generated from deterministic, language-specific public templates keyed by
category and candidate ordinal; it never includes `answer`/`distractor` ID
suffixes, expected labels, rationale, or the query. Candidate lifecycle/scope is
derived only from the phenomenon (`wrong_project_candidate`,
`superseded_memory`, `resolved_blocker`) and fixed candidate ordinal. Event time
anchors deterministic created/updated timestamps. This projection is a new
measurement fixture, not a claim that the original multi-family case was
already a canonical memory-retrieval task.

The projection is byte-deterministic, source-fingerprinted, and includes no
HOLDOUT-derived bytes. It is used for all three arms.

## Frozen selector

Input is project scope plus the common budget. Task/query text is ignored.

Candidate pool is the same scope-safe canonical read surface as V1: ACTIVE
global plus current-project memories and open typed requirements/blockers for
the project. Forbidden, foreign-project, superseded, resolved, and archived
records are excluded.

Ranking is deterministic:

1. open typed state items by `updated_at` descending, then ID lexical;
2. memories by `updated_at` descending, `created_at` descending, then ID
   lexical.

Items are appended only when the exact rendered result remains within 1920
usable conservative tokens and 24,000 UTF-8 bytes. No embeddings, lexical
score, graph, randomness, or ranking-time clock read is allowed. Output contains
only the normalized selected IDs/items and rendered-size accounting required by
the harness.

## Pre-registered phenomenon classification

This table is frozen before the first measurement.

| Phenomenon | Class | Metadata-based reason |
|---|---|---|
| explicit_decision | recency-favorable | A newly explicit commitment is expected to be useful while recent. |
| preference | recency-favorable | A current preference is normally represented by its latest active form. |
| lesson | neutral | Usefulness depends on relevance, not uniformly on age. |
| requirement | recency-favorable | Open requirements are explicitly prioritized by the selector. |
| suggestion | neutral | A suggestion is neither necessarily active nor age-sensitive. |
| hypothetical | recency-hostile | Recent hypothetical text is not an active commitment. |
| question | recency-hostile | A recent question is not itself durable answer context. |
| negation | recency-hostile | Surface recency can retain the negated candidate without semantic understanding. |
| correction | recency-favorable | The latest active correction should supersede older information. |
| quoted_material | recency-hostile | Recent quoted text is not speaker-owned canonical truth. |
| assistant_proposal | recency-hostile | Recent assistant proposals are not user commitments. |
| old_critical_decision | recency-hostile | The required decision is intentionally old and critical. |
| irrelevant_recent_memory | recency-hostile | A recent distractor is hostile by construction. |
| wrong_project_candidate | neutral | Scope filtering, not recency, must decide the outcome. |
| superseded_memory | neutral | Lifecycle filtering, not recency, must exclude it. |
| resolved_blocker | neutral | Lifecycle/state filtering, not recency, must exclude it. |
| ambiguous_reference | neutral | Correct behavior is abstention rather than age-based selection. |

## Frozen reporting and decisions

Use only existing IG01-C retrieval/context metrics: precision, recall, F1, MRR,
noise, token waste, context precision, and mandatory recall/coverage. Report
aggregate, all 17 phenomena, `en`/`tr`/`tr-en`, and the six-case abstention set.
At equal budget report paired per-case wins/ties/losses versus V1 and V2. No
significance claim is permitted.

- **S:** recency must be clearly worse on the pre-registered recency-hostile
  subset; otherwise stop conclusions and audit evaluator/corpus leakage.
- **F1:** recency >= V2 on aggregate precision and aggregate recall means “V2
  not shown to add value over recency on ig01f-recency-v1.” Record only; no
  tuning.
- **F2:** recency >= V1 on aggregate means a finding about V1 value on this
  derived corpus.
- **F3:** V2 clearly below recency on recency-favorable phenomena means suspected
  V2 regression; record/open an issue, do not fix here.

Recency losing overall is weak evidence because the source phenomena include
recent distractors. Recency winning or tying is strong evidence. Limitations
must state that the corpus is synthetic, intentionally recency-hostile, derived
from multi-family cases, and contains no real-use data.
