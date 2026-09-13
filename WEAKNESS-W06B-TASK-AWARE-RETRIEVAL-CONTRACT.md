# W-06B — Task-Aware Retrieval Quality Contract

**Status:** CONTRACT / IMPLEMENTATION NOT AUTHORIZED  
**Program:** Engineering Weak-Point Improvement Goal  
**Phase 20:** FROZEN / LOCKED  
**V2 runtime:** SHADOW  
**Predecessors:** W-06A (V1 bootstrap slice, SHIP), W-09 (evaluation evidence integrity, SHIP), W-09A (retrieval evaluation truth foundation, SHIP)

## 1. Problem and objective

W-06 remains the principal retrieval-quality weakness. The current V1 paths rank memories with fixed type, confidence, freshness and lexical signals, while the task itself is not an input to the active V1 compiler. W-09A now provides an exact, reproducible V1/V2 measurement boundary; its public evidence remains weak (V1 precision 0.1723, V2 precision 0.1472) and V2 remains shadow-only. This package may improve the bounded V1 retrieval/ranking behavior, but may not promote V2 or alter the Phase 20 boundary.

The objective is a task-aware, minimum-sufficient-context ranking path whose improvement is demonstrated against the frozen W-09A corpus and baseline, while preserving project/lifecycle/authority safety, deterministic output, bounded latency and token use, and a single rollback switch.

## 2. Bounded implementation surface

Implementation may change only the explicitly selected V1 ranking/retrieval surfaces and focused tests/evaluation adapters required to measure them:

- `scripts/context-compiler.py` V1 bootstrap ranking (`ContextCompiler._rank_memories`, lines 442–503) and its task/state relevance input boundary;
- `scripts/memory-retriever.py` `MemoryRetriever.search`/`get_by_type` (lines 110–213), only if the contract-selected V1 query path uses them;
- `scripts/hybrid-search.py` `HybridSearchEngine.search`/`_merge_results` (lines 52–199), only if the contract-selected path uses it;
- the existing V1 evaluation adapter and W-09A evaluation-only reporting/tests, without changing corpus labels or holdout data.
- `brain_eleven/runtime/storage.py` `RuntimeConfig.load` additive
  `retrieval_mode` resolution and bounded telemetry;
- `brain_eleven/runtime/context.py` UserPromptSubmit gate and bounded
  `TaskNeedInput` handoff, plus SessionStart legacy parity;
- `brain_eleven/runtime/service.py` `/api/context` and
  `brain_eleven/runtime/launcher.py` parity/rollback tests;
- native hook/install template surfaces only for wiring and parity evidence.

Before implementation, the package report must identify the exact active production caller path and may narrow this list. Unused legacy search modules must not be modified merely because they are in the inventory.

The direct legacy SessionStart templates remain a V1-only path and are not
converted to W-06B in this package. W-06B applies only to the native
UserPromptSubmit `/api/context` path described in §3; the runtime files above
are therefore an authorized part of the gate/handoff implementation, not an
unbounded architecture rewrite.

No changes are authorized to `context_router`, `context_compiler_v2`, V2 provider behavior, embedding providers, capture/worker paths, MemoryStore/StateStore/ProjectRegistry authority, lifecycle mutation, Phase 20, or unrelated architecture consolidation.

## 3. Runtime handoff and gate ownership

The installed SessionStart template invokes `scripts/context-compiler.py` directly (`templates/claude/hooks/brain-eleven-session-start:20`); the local legacy hook likewise invokes the compiler (`.claude/hooks/session-start.sh:52–65`). The native runtime path is separate and is the only bounded handoff for W-06B: `brain_eleven/runtime/service.py:213–218` calls `compile_context`, and `brain_eleven/runtime/context.py:60–65` routes `event=SessionStart` to `compile_bootstrap`. `compile_bootstrap` currently loads the legacy `ContextCompiler` (`context.py:19–40`) and is therefore V1. For `UserPromptSubmit`, `compile_context` validates mode/project, composes `TaskStateComposer(vault, project_root).compose(request)` (`context.py:66–75`), then calls `compile_task`; the task-aware input handoff must begin from these trusted fields, not from an untrusted scope override.

The W-06B gate is owned by the vault runtime configuration at `.brain-eleven/runtime/config.json`, loaded through `RuntimeConfig` (`brain_eleven/runtime/storage.py:40–61`). The additive key is `retrieval_mode`. Its only allowed values are `V1_LEGACY` (default; always used for SessionStart) and `W06B_TASK_AWARE` (permitted only for the bounded UserPromptSubmit task-aware entrypoint). Missing, malformed, unknown or unreadable `retrieval_mode` resolves fail-closed to `V1_LEGACY` and emits only bounded telemetry code `RETRIEVAL_MODE_INVALID`; it must never widen scope or throw raw configuration contents into telemetry. The existing rollout `mode` (`OFF`, `SHADOW`, `CANARY`, `ACTIVE`) is not this gate and must not be repurposed.

The exact handoff is: trusted `project_root` + request/session/turn from the native payload -> `allowed(vault, project_root)` -> `TaskStateComposer(vault, project_root).compose(request)` -> bounded `TaskNeedInput` -> W-06B ranking. The task input carries only the task ID, resolved project ID, bounded intent, continuation flag, sorted bounded entities and needs, and schema version defined in §4.2. Existing `ContextRouter`, `AuthorityResolver`, lifecycle policy and canonical source revisions remain authoritative. `compile_bootstrap`/SessionStart remains V1 regardless of the W-06B key.

Rollback is one atomic config write of `retrieval_mode=V1_LEGACY`; it must be verified through the same `/api/context` path (`service.py:213–218`) with `event=UserPromptSubmit`, and must show legacy provider identity plus no W-06B selection.

## 3. Current implementation evidence

### 3.1 V1 SessionStart compiler

`scripts/context-compiler.py:7–12` documents the active pipeline: load validated memory, load continuity files, rank by type priority/freshness/confidence with bounded current-state relevance, fetch related notes, and write the bootstrap.

`ContextCompiler.__init__` at `scripts/context-compiler.py:80–106` binds the vault, `MemoryStore`, `StateResolver`, project ID and retrieval scope. `_load_validated_memories` at `112–123` reads the canonical store revision and validated records. `_ensure_output_is_current` at `160–182` rejects memory or state revision races before publishing a derived bootstrap.

The W-06A ranking implementation is at `scripts/context-compiler.py:442–503`: it filters by `filter_memories` with project/scope, excludes non-active records at `460–464`, computes type priority (`445–450`), freshness (`470`), quality/confidence (`472–480`), and state lexical relevance (`457`, `482–490`), then sorts by scope tier, descending score and `_stable_memory_key` (`493–500`). This provides deterministic tie-breaking, but the query is only resolved structured state (`333–381`), not the current user task.

### 3.2 Legacy direct retriever

`scripts/memory-retriever.py:31–55` defines `SearchResult` and fixed type priorities. `_similarity_score` at `73–84` is word-overlap Jaccard; `_freshness_score` at `86–108` is age-based. `MemoryRetriever.search` at `110–170` filters scope/lifecycle (`121–131`), rejects similarity below `0.05` (`133–139`), computes a fixed formula—similarity 40%, confidence 30%, type priority 20%, freshness 10%—at `141–147`, and sorts only by descending score at `167–170`; equal scores therefore inherit input order. `get_by_type` has a separate confidence/freshness formula at `172–213`.

### 3.3 Legacy hybrid search

`scripts/hybrid-search.py:36–46` uses fixed lexical/semantic weights 0.40/0.60. `search` at `52–113` filters scope, calls lexical search, optionally calls semantic search only when a real provider is available (`95–103`), merges results and sorts only by descending `combined_score` (`105–113`). `_merge_results` at `119–199` combines channels, normalizes unavailable semantic search to lexical-only (`174–183`), then applies a novelty boost (`185–197`). The current fallback is intentionally lexical and must remain explicit; deterministic/hash vectors must not be introduced as semantic evidence.

### 3.4 V2 is not a W-06B target

`context_router/router.py:89–112` already normalizes candidates with per-source budgets and candidate-ID tie-breaking. Its retrieval calls at `288–341` use trusted task-derived scope/query plans and re-check source revisions at `341–352`. `context_router/policy.py:29–70` maps task intent to bounded profiles, preserves caller-authorized history mode, enforces project scope and lifecycle status. `context_compiler_v2/compiler.py:91–161` validates upstream status, applies budgets and cache manifests; `252–280` rejects stale inputs and reports bounded status. These remain shadow-only and are evidence/reference boundaries, not implementation targets.

### 3.5 Measurement boundary

`evals/baseline.py:1–6` states that V1 does not receive the task prompt and exposes this limitation. `BaselineContextProvider.select` at `147–169` invokes the current compiler with project/scope only. `evals/compiler_v2_provider.py:32–83` is the separate task-aware V2 provider. W-09A freezes `evals/corpus-v2/` DEV/TEST/HOLDOUT, source/corpus/candidate fingerprints, K, provider/config/seed and hard safety gates. W-06B must consume that boundary rather than replace it.

## 4. Frozen retrieval contract

### 4.1 Provider and configuration

The initial implementation uses deterministic lexical/task-feature signals available locally. No embedding provider migration or new model is authorized. If an existing real semantic provider is measured, its provider ID and availability must be recorded; unavailable means explicit `SEMANTIC_UNAVAILABLE`/degraded status and never a synthetic score.

The following are frozen for one W-06B revision: provider ID and availability, source revision, task-need model version, feature weights, K, scope/history options, token/latency budgets, normalization, missing-field policy and final tie-break. Any change requires a new package revision and a new DEV baseline.

### 4.2 Task-need input/output contract

The task-aware entrypoint receives a finite `TaskNeedInput` containing only:

```text
task_id: bounded non-empty identifier
project_id: string|null (already resolved by trusted task/project resolution)
intent: one of IMPLEMENT, MIGRATE, TEST, DEBUG, REVIEW, PLAN, DESIGN, RESEARCH, GENERAL
continuation: boolean
entities: sorted unique bounded strings (max 32)
needs: sorted unique bounded enum values (max 16)
raw_prompt: not retained; optional transient input only for deterministic extraction
schema_version: 1
```

The output is `TaskNeedResult`:

```text
status: READY | NO_NEED | AMBIGUOUS | UNAVAILABLE | INVALID
profile: bounded profile enum or null
needs: sorted unique bounded enum values
project_id: resolved project ID or null
error_code: content-free bounded code or null
schema_version: 1
```

Only `READY` may add task relevance signals. `NO_NEED` deterministically uses legacy ranking with no task signal. `AMBIGUOUS`, `UNAVAILABLE` and `INVALID` deterministically use legacy ranking, preserve the trusted caller scope/history, and expose only their bounded status/error code. They never guess a project, widen history, or select a broader retrieval scope. Unknown fields, overlong arrays, invalid enums or invalid identifiers produce `INVALID`.

The task-need extractor may consume the already resolved task model and bounded entity/intent fields. It must not persist raw prompts or candidate content. The existing trusted policy remains authoritative: `resolve_profile`, `resolve_history_mode` and `resolve_scope` in `context_router/policy.py:29–70` are reference rules.

### 4.3 Candidate eligibility and safety hard gates

Before scoring, every candidate must pass the existing scope filter and lifecycle policy. Required invariants:

- wrong-project leakage = 0;
- forbidden leakage = 0;
- superseded leakage = 0;
- resolved leakage = 0 when the selected history mode excludes it;
- secret/unsafe content leakage = 0;
- no candidate may be admitted solely because lexical or semantic similarity is high;
- canonical MemoryStore/StateStore/ProjectRegistry remain read-only authorities for retrieval;
- candidate source revision must be captured and checked before the result is published;
- no task prompt or candidate content is written to long-lived telemetry.

A single safety failure is a hard package failure and cannot be masked by aggregate precision/recall.

### 4.4 Ranking, minimum sufficient context and overflow

Ranking must expose separate signals, at minimum: task-need relevance, claim/content relevance, project relevance, authority/criticality, freshness, lifecycle eligibility, dependency/continuity relevance, redundancy penalty and deterministic identity/content tie-break. Freshness is one signal only; an old canonical decision may outrank a newer irrelevant note.

The result is bounded by **at most 5 memory items**, **at most 1,024 estimated output tokens**, and **at most 8,192 UTF-8 bytes** for the selected context payload. The 5-item bound preserves the current V1 bootstrap limit (`scripts/context-compiler.py:666`); the token/byte limits leave room for the task envelope and hook framing while preventing context growth from becoming a hidden budget sink. Measurement uses the same deterministic estimator and rendered UTF-8 byte count used by the selected provider; if the estimator is unavailable, status is `TOKEN_UNAVAILABLE` and the result is not promoted or scored as a successful budget pass.

The result must stop at minimum sufficient context. It must not select everything to improve recall. Required/must-include items from W-09A remain mandatory when eligible. If mandatory items alone exceed any frozen bound, return `INSUFFICIENT_BUDGET` with fields `{status, required_ids, omitted_ids, item_count, estimated_tokens, byte_count, budget_version}`; do not silently truncate or substitute forbidden/ineligible items. If optional items cannot fit, omit them deterministically with `OPTIONAL_BUDGET_EXHAUSTED`. An empty eligible set returns `EMPTY` with no error. Any scope/lifecycle safety failure returns `SAFETY_REJECTED` and no selected context.

The final ordering must be independent of input/file order. The tie-break is frozen as `(descending final score, source/type policy, memory_id, canonical content fingerprint)` and is covered by a fixed fixture test.

### 4.5 Rollback and runtime gate

The new ranking path must sit behind one explicit feature gate with states `V1_LEGACY` and `W06B_TASK_AWARE`. Default remains `V1_LEGACY` until package acceptance. One configuration change must restore legacy ranking without data migration or canonical writes. Rollback must be tested after a real W-06B selection and must preserve scope/lifecycle safety.

V2 remains `SHADOW`; no W-06B result may change SessionStart to V2 or alter V2 promotion status. Phase 20 remains locked.

## 5. Tuning and split discipline

- DEV: the only split permitted for feature/weight/threshold iteration.
- TEST: frozen public architecture-decision comparison; read only after DEV choices are frozen.
- HOLDOUT: never read for tuning, fixture repair, threshold selection or implementation decisions; final audit only after the package is otherwise frozen.
- W-09A corpus labels, answerability decisions, candidate snapshots and holdout files are immutable. Any change requires a new corpus version and independent contract review.
- V1 baseline and W-06B outputs must run on exactly the same cases, candidate pools, K and report normalization.
- Before tuning, record an exact W-06B pre-change V1 baseline with source/corpus/candidate fingerprints, provider/config/task-need identifiers, metrics and safety statuses.

## 6. Targets and exit gates

### 6.1 Minimum quality targets

The package must improve over the exact V1 baseline on DEV and then demonstrate on TEST:

- context precision >= 0.60 minimum contract threshold;
- mandatory recall >= 0.80;
- MRR non-regression against V1 and documented improvement where task-aware cases are answerable;
- noise ratio and token waste materially reduced or explicitly shown non-regressed;
- V1 task-aware provider precision > legacy V1 precision on TEST, with mandatory recall >= the accepted V1 threshold.

The stronger graduation target (precision >=0.75, mandatory recall >=0.90) is not silently substituted into this package; if adopted it requires a versioned contract amendment.

### 6.2 Hard safety and operational targets

- every W-09A safety leakage counter = 0 on DEV, TEST and final HOLDOUT audit;
- deterministic repeated run and shuffled-input outputs are identical;
- p95 task-aware selection latency is **<=250 ms** on the frozen evaluation harness hardware/profile, measured over at least 30 repeated runs per public split with warm and cold-start values reported separately; exceeding the limit is a visible operational failure;
- selected context stays within **5 items, 1,024 estimated tokens and 8,192 UTF-8 bytes**;
- unavailable provider/estimator, malformed optional fields and invalid gate configuration produce explicit bounded statuses (`SEMANTIC_UNAVAILABLE`, `TOKEN_UNAVAILABLE`, `INVALID`, `RETRIEVAL_MODE_UNAVAILABLE`) and never silently count as a quality success;
- mandatory overflow returns `INSUFFICIENT_BUDGET` with no unsafe fallback; optional overflow is deterministic omission;
- rollback succeeds and legacy output remains available;
- no canonical writes, authority changes, or telemetry content leakage.

### 6.3 Required tests/evidence

1. **Contract and baseline:** exact revision, provider/config/task-need/K/budget fingerprints, V1 baseline reports and split hashes.
2. **Runtime gate/handoff:** `RuntimeConfig` missing/invalid/allowed-value resolution, `compile_context` UserPromptSubmit handoff, SessionStart legacy parity, `/api/context` and launcher parity, and atomic rollback to `V1_LEGACY`.
3. **Safety:** wrong project, global/project boundary, inactive/superseded/resolved records, forbidden IDs, unavailable/corrupt source and stale revision cases.
4. **Quality:** exact/rephrase/related/old-critical/recent-irrelevant/same-keyword/distractor/continuation cases; mandatory recall, precision, MRR, noise and token waste.
5. **Determinism:** repeat run, shuffled input, equal-score and malformed-field fixtures.
6. **Budget:** K, token/byte cap, mandatory overflow and p95 latency tests.
7. **Rollback:** W06B on/off parity and safety regression.
8. **Regression:** focused current retrieval/context/router/authority tests, full suite, critical flake8 (`E9,F63,F7,F82`), compile/import sanity and `git diff --check`.
9. **Independent review:** reviewer reads contract, exact diff, baseline/after reports, safety failures and rollback evidence without relying on implementer reasoning.

## 7. Package report template

```text
PACKAGE: W-06B
REVISION: <exact implementation/review SHA>
OBJECTIVE: <bounded task-aware V1 retrieval improvement>
FILES CHANGED: <exact paths>
ROOT CAUSES ADDRESSED: <task-unaware ranking, unstable ties, noise/token waste>
TESTS ADDED: <focused tests>
TESTS EXECUTED: <commands and exact results>
QUALITY METRICS BEFORE: <exact V1 DEV/TEST/HOLDOUT-audit values>
QUALITY METRICS AFTER: <W06B values on same cases>
SAFETY METRICS: <all hard gates and operational statuses>
ROLLBACK EVIDENCE: <V1 legacy restoration>
KNOWN LIMITATIONS: <provider/task ambiguity/latency limits>
OPEN FAILURES: <none or exact failures>
INDEPENDENT REVIEW: <SHIP / FIX-FIRST / RETHINK, exact review SHA>
SCORE BEFORE: <retrieval/context score>
SCORE AFTER: <evidence-backed score, no unsupported increase>
VERDICT: <SHIP / FIX-FIRST / RETHINK>
```

## 8. Explicit exclusions

No embedding migration, local Qwen integration, provider replacement, V2 promotion, context-router redesign, context-compiler-v2 changes, capture/worker work, reminder/continuity work, MemoryStore/StateStore/ProjectRegistry implementation, lifecycle mutation, architecture-wide rewrite, Phase 20 work or unrelated cleanup.

## 9. Contract exit gate

Implementation cannot begin until this contract has an independent read-only review with exact verdict `SHIP`. After implementation, W-06B itself remains open until its separate focused evidence and independent implementation review return `SHIP`. A weak TEST result, any hard safety leak, unexplained provider unavailability, missing rollback evidence or holdout contamination is `FIX-FIRST`/`RETHINK`, never silently accepted.

**Contract status: REVIEW PENDING — implementation has not started.**
