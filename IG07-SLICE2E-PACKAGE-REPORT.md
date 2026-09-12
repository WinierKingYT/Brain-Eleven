# IG-07 Slice 2E — E1 + E2 Package Report

**PACKAGE:** IG-07 / Slice 2E (`task_model.py` inversion)
**IMPLEMENTATION REVISION:** `c0fe23f`
**EVIDENCE REVISION:** `7aad3d0`
**BASELINE REVISION:** `88773e7`
**OBJECTIVE:** Move the deterministic task contract into
`brain_eleven.runtime.task` while preserving every legacy import, exception,
JSON, evaluator, and task-state-context behavior.

## FILES CHANGED

- `brain_eleven/runtime/task.py` — canonical implementation; staged blob is
  byte-identical to the pre-inversion `scripts/task_model.py` implementation.
- `scripts/task_model.py` — thin cached loader/re-export/direct-CLI adapter,
  including historical `ProjectRegistry` and `ProjectRegistryError` names.
- `tests/test_task_model_package_migration.py` — identity, adapter-only,
  context immutability, CLI, and evaluation parity evidence.
- `IG07-SLICE2E-E1-CONTRACT.md` — public export and legacy-name matrix.
- `evals/reports/ig07-slice2e/before-*.json` and `after-*.json` — exact
  smoke/public/holdout evidence artifacts.

No changes were made to `scripts/task_state_context.py`,
`authority/serialization.py`, `evals/task_state_eval.py`, their case labels,
the holdout corpus, or the canonical ProjectRegistry/StateStore/MemoryStore
implementations.

## ROOT CAUSES ADDRESSED

- `task_model.py` was the remaining high-blast-radius runtime contract whose
  implementation authority lived under `scripts/`.
- Package callers could not share one canonical task-model object identity with
  historical `scripts.task_model` and bare `task_model` imports.
- The historical registry exports from `task_model` needed an explicit
  compatibility guarantee.

## E1 BASELINE

Baseline was recorded at exact revision `88773e7` before production inversion:

| Suite | Artifact | Gate | Task cases | State cases |
|---|---|---|---:|---:|
| smoke | `evals/reports/ig07-slice2e/before-smoke.json` | pass | 20 | 20 |
| public | `evals/reports/ig07-slice2e/before-public.json` | pass | 24 | 24 |
| holdout | `evals/reports/ig07-slice2e/before-holdout.json` | pass | 4 | 4 |

The ten-file pre-E2 focused suite passed **107 tests**. The baseline contract
and export matrix are in `IG07-SLICE2E-E1-CONTRACT.md`.

## E2 IMPLEMENTATION

The canonical package module was created by copying the pre-inversion script
implementation. A staged blob comparison returned:

```text
canonical_matches_pre_inversion_script_bytes=True
old_bytes=27428 new_bytes=27428
```

The adapter contains only root-path setup, canonical loading/cache,
compatibility aliases, and direct `main()` delegation. It has zero class
definitions, zero analyzer/rule/validation implementation, zero JSON/file
write path, and zero MemoryStore/StateStore access.

`task_state_context.py` remains unchanged and now resolves the same canonical
objects through its existing `scripts.task_model`/bare fallback imports.

## IDENTITY AND PARITY EVIDENCE

The migration test verifies package/adapter/bare identity for:

- `TaskAnalyzer`, `TaskEnvelope`, `Evidence`, `ProjectResolution`;
- both task error classes;
- all schema/namespace/rule-set constants;
- `ProjectRegistry` and `ProjectRegistryError` compatibility exports;
- `utc_now`, `new_task_id`, `resolve_project`, `validate_task`, and
  `render_task_json`;
- `TaskEnvelope.from_dict.__func__` identity;
- unchanged `task_state_context.py` working-tree diff;
- direct script CLI and `python -m brain_eleven.runtime.task` contract parity.

## EVALUATION BEFORE / AFTER

After reports were generated with the same evaluator and compared as complete
JSON objects against the immutable before artifacts:

| Suite | After artifact | Exact JSON equality | Gate | Task/state cases |
|---|---|---:|---|---:|
| smoke | `evals/reports/ig07-slice2e/after-smoke.json` | **True** | pass | 20 / 20 |
| public | `evals/reports/ig07-slice2e/after-public.json` | **True** | pass | 24 / 24 |
| holdout | `evals/reports/ig07-slice2e/after-holdout.json` | **True** | pass | 4 / 4 |

All suites retained task/state pass rate `1.0` and wrong-project state leakage
rate `0.0`. `evals/task_state_eval.py` and all eval source/cases remained
unchanged; only the evidence report artifacts were added.

## TESTS EXECUTED

- E2 migration evidence + ten-file focused suite: **114 passed**.
- Full suite, first run: 942 passed and one cold native SessionStart timing
  failure.
- The failing test passed in isolation in 3.29s.
- Full suite, exact HEAD rerun: **943 passed, 2 warnings** in 173.55s.
- Critical flake8 (`E9,F63,F7,F82`) on package/adapter/evidence tests: **PASS**.
- `compileall`: **PASS**.
- `git diff --check`: **PASS**.
- Staged implementation blob parity: **PASS**.
- `task_state_context.py` diff: **empty**.
- `evals/task_state_eval.py` source diff: **empty**.

Warnings are the existing FastAPI/Starlette dependency deprecations. The one
cold-start failure was not reproducible on isolated rerun or the complete
second run; it is recorded rather than hidden.

## SAFETY METRICS

- New canonical persistence authority: **0**.
- Task model writes to MemoryStore/StateStore: **0**.
- Analyzer registry mutation: **0**; project resolution remains read-only.
- `task_state_context.py` compatibility shim added: **0**.
- Holdout case/label/threshold changes: **0**.
- Authority serialization/eval source changes: **0**.
- Cross-project task-state leakage: **0** in smoke/public/holdout reports.

## KNOWN LIMITATIONS / OPEN FAILURES

- `task_state_context.py` remains a separate 26+ caller migration and was
  intentionally not moved.
- The first full-suite run exposed one nonpersistent cold-start timing failure;
  no code change was made to mask or loosen that test.
- Independent byte-diff, authority review, and holdout review are pending.
- No new P0/P1 functional failure is open.

## INDEPENDENT REVIEW

**SHIP.** See `IG07-SLICE2E-INDEPENDENT-REVIEW.md` (2026-09-12). The
byte-identical canonical source, adapter-only AST, legacy identity,
untouched task-state context, and exact holdout before/after reports were
each independently re-verified against the repository, not accepted on this
report's word.

## SCORE BEFORE / AFTER

- Task-model package authority: not scored until independent review.
- Task understanding, extraction, retrieval, daily-use and Phase 20 status:
  unchanged by this inversion.

## VERDICT

**SHIP** — E1 and E2 implementation/evidence are complete and pushed;
independent review (`IG07-SLICE2E-INDEPENDENT-REVIEW.md`, 2026-09-12)
re-verified every load-bearing claim directly against the repository.
IG-07 Slice 2E is closed.
