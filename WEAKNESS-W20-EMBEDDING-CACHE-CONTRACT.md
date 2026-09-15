# W-20 — Legacy Embedding Cache Durability Contract

**Status:** CONTRACT REVIEW PENDING — implementation not started

**Program:** Engineering Weak-Point Improvement Goal

**Phase 20:** FROZEN / LOCKED — **V2:** SHADOW

## Objective

Make the existing legacy embedding cache durable and concurrency-safe without
changing embedding providers, vector values, ranking weights or retrieval
selection behavior.

## Observed weakness

The Docker search path still constructs a long-lived legacy
`EmbeddingGenerator`. `scripts/embedding-generator.py::_save_cache` writes
`embeddings.json` directly with `json.dump`, without a sidecar lock, atomic
replace, flush/fsync or parent-directory creation. A failed write can leave a
truncated cache; synchronized writers can lose one another's entries. The
long-lived reader only loads the cache at construction, and `clear_cache()`
currently clears memory without a durable disk deletion.

## Bounded behavior contract

1. Preserve the existing cache path, JSON schema, embedding provenance
   fields, provider availability behavior and vector validation. No random or
   local-model semantic fallback may be introduced.
2. `_save_cache` must serialize through one cache sidecar lock, write a
   temporary file in the same directory, flush and fsync it, then atomically
   replace the destination. Parent-directory creation must be explicit and
   contained to the vault cache directory.
3. A concurrent save must not silently lose entries written by another
   generator. Under the lock, load a valid current cache and merge compatible
   entries deterministically before publication; malformed entries remain
   ignored by existing provenance validation. If the same memory ID contains
   incompatible content/provenance, fail visibly and leave the prior valid
   file unchanged rather than choosing a silent winner.
4. `clear_cache()` must persist an empty cache through the same atomic path so
   a new generator cannot resurrect cleared vectors. A successful `save()` or
   `clear_cache()` returns an explicit success result; a write failure is
   visible to the caller and the prior valid file remains intact.
5. Long-lived readers must not silently claim newly written vectors are
   available. Add an explicit `refresh_cache()` operation and call it at the
   existing semantic-search boundary before reading cached vectors. Refresh
   may inspect a cache fingerprint and reload under the lock; it must not add
   background polling or alter search ranking.
6. Cache corruption or unavailable persistence remains explicit and bounded:
   no prompt, memory content, secret, API key or exception text is persisted.
   Canonical MemoryStore/StateStore/ProjectRegistry revisions are untouched.

## Required tests

- interrupted/failed save leaves the previous cache valid;
- concurrent saves retain both compatible entries;
- incompatible same-ID concurrent save is visible and preserves the prior
  valid entry;
- parent cache directory is created safely;
- a newly constructed generator reads the atomically published cache;
- durable `clear_cache()` remains cleared after reconstruction and reports
  write failure explicitly;
- semantic-search refresh sees an external update without process restart;
- malformed/provenance-mismatched entries remain rejected;
- cache operations do not change canonical revisions or ranking outputs;
- existing `tests/test_phase7_semantic_search.py` behavior remains unchanged.

Run the focused semantic-search/cache suites, then full `pytest tests -q`,
critical flake8 (`E9,F63,F7,F82`), compileall and `git diff --check` at an
exact committed revision. Add process-level fault and concurrency evidence,
not only unit mocks.

## Scope exclusions

This package does not select an embedding provider, add Qwen/local models,
change hybrid/semantic ranking, tune retrieval weights, migrate V2, alter
canonical stores, change task understanding, or unlock Phase 20. Any live
reader API change must remain an explicit cache-refresh surface only.

## Exit gate

W-20 may be marked `SHIP` only after contract-independent review returns
`SHIP`, implementation/tests satisfy durability and no-loss evidence, exact
focused/full regression is green, and an independent read-only implementation
review returns exactly `SHIP`.

Until then: **W-20 = OPEN / NOT ACCEPTED**.

**Contract status: REVIEW PENDING — implementation başlamadı.**
