# W-08C State Reference Commit Guard

PACKAGE: W-08C  
REVISION: `200621b`  
OBJECTIVE: Make StateStore memory-reference commits linearizable against the canonical MemoryStore lock.

## FILES CHANGED

- `scripts/state_store.py` — added a held `memory_store_lock` guard for `add_memory_reference()` and `add_blocker(..., memory_ref=...)`, bounded snapshot validation, closed-world lifecycle checks, and typed guard failures.
- `scripts/state_resolver.py` — classifies deleted and unknown-status targets as `dangling`; existing result shape is unchanged.
- `tests/test_w08c_state_reference_guard.py` — policy, lifecycle, scope, lock ordering, race, CAS, replay, corruption, timeout, privacy, and identity evidence.

No `MemoryStore`, `ProjectRegistry`, package bridge, evaluator, corpus, state schema, audit-event schema, or Phase 20 file was changed.

## ROOT CAUSES ADDRESSED

- Memory reference validation previously ran before the state transaction without holding the canonical memory lock.
- A concurrent memory writer could therefore change the validated record between validation and state commit.
- Deleted and unknown-status canonical records were not classified by the state reference policy.

## TESTS ADDED

19 focused tests cover:

- global/project scope and existing state JSON shape;
- missing, wrong-project, deleted, unknown-status, and rejected-bucket targets;
- resolved/superseded/legacy status compatibility;
- resolver classification;
- stale state CAS and duplicate replay effects;
- typed memory-lock timeout and corrupt-memory failures;
- state-lock timeout preservation;
- normal `MemoryStore.transact` writer serialization;
- blocker references using the same guard;
- bounded privacy and package/legacy identity.

## TESTS EXECUTED

At exact revision `200621b`:

- Focused W-08C and required state/authority suite: **90 passed**.
- Full suite: **1037 passed, 2 pre-existing dependency warnings** in 218.29s.
- `tests/test_evaluation_baseline_snapshot.py`: **5 passed**.
- Task-state smoke/public/holdout reports: **byte-identical** to the frozen `evals/reports/ig07-slice2e/before-*.json` reports. Each suite exited 0.
- Critical flake8 (`E9,F63,F7,F82`): **0**.
- `compileall`: **0**.
- `git diff --check`: **0**.

## QUALITY METRICS BEFORE / AFTER

- State/reference consistency: **6.5/10 provisional → pending independent review**.
- No retrieval, extraction, capture, V2, or Phase 20 metric was changed.

## SAFETY METRICS

- Missing, deleted, unknown-status, rejected-bucket, and wrong-project references: rejected without state revision or event changes.
- Resolved and superseded historical references: remain valid when scope matches.
- Memory lock timeout / snapshot mismatch: typed bounded failure; no state write.
- State lock timeout and stale state CAS: preserve existing typed behavior.
- Normal memory writer: waits behind the memory-lock → state-lock transaction order.
- New guard metadata is ephemeral; memory content, project roots, prompts, secrets, and memory revision are not persisted to state or audit events.
- No direct canonical file write was introduced.

## KNOWN LIMITATIONS

- Later lifecycle changes remain visible through `StateResolver`; W-08D owns lifecycle/API coordination.
- The new `StateReferenceConflict` lives in the legacy `scripts.state_store` implementation because this package is explicitly bounded against bridge changes. The existing CLI module and package bridge were intentionally left untouched and require independent review against the contract's desired `MEMORY_REFERENCE_CONFLICT` CLI mapping.

## OPEN FAILURES

- None found by local focused, full, static, or task-state baseline checks.
- Independent review is still required; the CLI mapping/bridge-scope point above remains an explicit review item.

## INDEPENDENT REVIEW

**PENDING.** Implementer does not self-SHIP.

## SCORE BEFORE / AFTER

- Before: **6.5/10 provisional**.
- After: **pending independent review**.

## VERDICT

**REVIEW PENDING**
