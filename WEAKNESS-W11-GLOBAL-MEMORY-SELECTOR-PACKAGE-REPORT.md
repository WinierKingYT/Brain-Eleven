# W-11 — Global Memory Selector Package Report

**PACKAGE:** W-11  
**REVISION:** `2efb9435062857b34facaf43dd8bd33b4faa1326`  
**OBJECTIVE:** Make the opt-in W06B task-aware selector honor canonical global
scope records without widening project scope or changing ranking behavior.

**PROGRAM STATE:** Phase 20 `FROZEN / LOCKED`; V2 `SHADOW`.

## Files changed

- `brain_eleven/runtime/task_aware.py`
- `tests/test_w06b_task_aware.py`

The W06B selector now uses the package-owned `infer_memory_scope()` surface.
No MemoryStore, StateStore, ProjectRegistry, V1 default path, embedding,
HOLDOUT, retrieval weight, V2, or Phase 20 file changed.

## Root causes addressed

`select()` compared the raw `project_id` field with `{None, task_project}`.
Canonical global records use `scope="global", project_id=""`, so they were
discarded after the compiler had already returned them. The selector now
accepts canonical global scope and project records only when their normalized
project ID matches the task project.

## Tests added

`test_canonical_global_records_are_selected_without_cross_project_leakage`
covers a canonical empty-ID global record, a legacy global record with no
project field, and a foreign project record in the same ranked input.

## Tests executed

- New regression before implementation: **failed as expected** because the
  canonical empty-ID global record was omitted.
- `pytest tests/test_w06b_task_aware.py -q`: **9 passed**.
- Focused W06B/context-router/scope-migration suite: **40 passed**.
- W06C contract suite: **23 passed**.
- `pytest tests -q`: **1179 passed, 2 dependency warnings** at exact revision
  `2efb943` (the increase from 1178 is the new regression test).
- Critical flake8 (`E9,F63,F7,F82`) on touched code/tests: **passed**.
- `compileall` on touched code/tests: **passed**.
- `git diff --check`: **passed**.

## Quality metrics before / after

| Measure | Before W-11 | After W-11 |
| --- | --- | --- |
| Canonical global record (`project_id=""`) selected by W06B | 0 | 1 or more when eligible |
| Legacy global record selected | Yes when field missing | Preserved |
| Foreign project record selected | 0 | 0 |
| Ranking/limits/provider contract | Baseline | Unchanged |

## Safety metrics

- Wrong-project selection in the new isolation test: **0**.
- Default `V1_LEGACY` path changed: **0**.
- Canonical writes or model authority introduced: **0**.
- HOLDOUT corpus/labels/thresholds changed: **0**.
- V2 promotion or Phase 20 unlock: **0**.

## Known limitations

- W06B remains an explicit opt-in path and is not a retrieval-quality
  graduation. The existing W06 evaluation still remains below the V1 target;
  this package fixes only scope normalization.
- Native default runtime remains V1 and product V2 remains `SHADOW`.

## Open failures

- No W-11 focused or full-suite failure remains.
- Independent read-only review is still required before package closure.

## Independent review

**SHIP** — independent read-only review at exact implementation revision
`2efb9435062857b34facaf43dd8bd33b4faa1326`; report revision
`5daca79bb65351bd37f956e30fc0548b2fdbb6ac`. The reviewer verified canonical
scope use, global/foreign-project behavior, unchanged safety and ranking
contracts, and the 1179-test evidence.

## Score before / after

- Retrieval correctness: **6.0 / 10 before**; no score increase is claimed
  before independent review.
- Retrieval quality: unchanged; this package does not tune ranking or quality
  metrics.

## Verdict

**SHIP**
