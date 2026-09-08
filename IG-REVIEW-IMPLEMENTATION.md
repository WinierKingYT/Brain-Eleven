# IG-00 review implementation record

Authority: **REVIEW**. This file records the bounded review work completed on
the IG-00 branch; it does not authorize IG-01 or Phase 20.

The semantic fallback was removed from production retrieval. Without a real
provider, semantic search returns no vector and hybrid search uses an explicit
lexical-only path. Cached embeddings require content hash, provider, model,
dimension, embedding schema version, source revision when available, and a
valid vector shape.

The remaining review-derived correctness fixes are:

- confidence is derived from named extraction signals and serialized as
  components;
- competing task intents are marked ambiguous with bounded confidence;
- continuity candidates have a 30-day age bound and recency signal;
- state candidates remain available for mandatory context while unmatched
  records receive lower relevance;
- graph-only candidates consume a separate graph budget;
- router, authority, and compiler derived caches use recent-access eviction;
- compiler telemetry distinguishes an audit-manifest hit from a compiled
  context hit;
- search cache identity includes content and revision fingerprints;
- the historical `MLRanker` name remains an alias for `HeuristicRanker`;
- IG-01 taxonomy and controlled semantic ranking tests are versioned.

These changes preserve canonical authority and keep V2 shadow-only. They do
not claim semantic extraction, correction resolution, task-aware quality, or
real-use graduation. Those remain explicit IG gates.

The exact-head follow-up at `0db7f5a2dd132b1e5e6e8248c2ee13032544845e` added
only four fail-closed router coverage tests and review-branch CI triggers.
Validation run 34264515612 passed at that SHA. The PRE-13 runtime workflow's
Ubuntu/Windows jobs passed, while its historical holdout quality job remains a
visible failure. This record is still not an independent review and does not
authorize IG-01.
