# W-20 — Legacy Embedding Cache Package Report

**PACKAGE:** W-20
**REVISION:** `db6ae44958427808d786768ca3dd99e1073f81fe`
**OBJECTIVE:** Make the legacy embedding cache durable, concurrency-safe and
refreshable without changing providers, ranking or canonical stores.
**CONTRACT:** `WEAKNESS-W20-EMBEDDING-CACHE-CONTRACT.md`, reviewed `SHIP` at
`515682c`.

## Files changed

- `scripts/embedding-generator.py`
- `scripts/semantic-search.py`
- `tests/test_w20_embedding_cache.py`

## Root causes addressed

The cache previously overwrote `embeddings.json` directly, could lose a
concurrent writer, left a truncated file after an interrupted write, and was
loaded only when a long-lived reader was constructed. `clear_cache()` also
cleared only in-memory state. The package now uses the existing sidecar lock,
same-directory atomic storage, explicit success results, compatible-entry
merging, durable clearing and an explicit semantic-search refresh boundary.

## Tests added

- Failed and process-crashed publication preserves the prior destination.
- Distinct concurrent processes retain both compatible entries.
- Incompatible same-ID provenance fails without overwriting the prior file.
- Compatible same-ID vectors use an order-independent stable tie-break.
- Parent creation and exactly one cache sidecar lock are verified.
- Durable clear, clear failure recovery and stale-writer suppression are
  covered.
- Long-lived semantic readers observe an external cache update without
  restart.
- Malformed/legacy entries remain rejected.
- Cache operations preserve canonical revision and ranking output.

## Tests executed

- W-20 + Phase 7 focused suite: **40 passed**
- Full suite at exact revision: **1318 passed, 4 skipped, 2 warnings**
- Critical flake8 (`E9,F63,F7,F82`): **PASS**
- compileall: **PASS**
- `git diff --check`: **PASS**
- Process-level crash and concurrent-writer evidence: **PASS**

The two warnings are existing dependency deprecation warnings from FastAPI/
Starlette test support; no W-20 warning was introduced.

## Quality metrics before/after

- Before: direct non-atomic cache writes, possible concurrent-entry loss,
  restart-only visibility for long-lived readers and non-durable clear.
- After: atomic locked publication, no-loss compatible merge, visible
  incompatible conflicts, durable clear and explicit refresh. Existing Phase 7
  ranking behavior remains unchanged on the same inputs.

## Safety metrics

- Canonical MemoryStore/StateStore/ProjectRegistry revisions changed by cache
  operations: **0**
- Wrong-project, forbidden, superseded or resolved memory leakage introduced:
  **0** (cache-only package)
- API keys, prompts, transcripts, memory content or exception text persisted
  in cache error output: **0**
- Provider selection, vector provenance validation and ranking weights changed:
  **0**

## Known limitations

The cache remains a legacy script surface; this package does not migrate the
embedding/search implementation into a new package. Provider selection,
retrieval tuning, V2 promotion, task-aware ranking, canonical stores and Phase
20 remain outside scope. A cache write with malformed existing JSON returns an
explicit failure and preserves that snapshot for operator recovery.

## Open failures

W-20 package failures: **none**. W-07B native trust/latency/dogfood and the
separately contracted W-21/W-22 V2 findings remain open outside this package.

## Independent review

Read-only implementation review at exact revision `db6ae44` returned
**SHIP**. It independently verified atomic crash preservation, process
concurrency, deterministic compatible-entry selection, incompatible-entry
preservation, durable clear, stale-writer suppression, refresh behavior,
canonical isolation, focused tests and static gates. No P0, P1 or P2 findings
remain.

## Score before/after

- Persistence/concurrency: **8.5 → 8.7** (legacy cache publication is now
  locked, atomic and no-loss under the covered races)
- Semantic retrieval correctness: **unchanged at 6.0** (provider quality and
  task-aware retrieval remain open)
- Other scorecard dimensions: unchanged.

## Verdict

**SHIP**
