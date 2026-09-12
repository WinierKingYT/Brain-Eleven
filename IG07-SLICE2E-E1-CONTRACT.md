# IG-07 Slice 2E — E1 Contract and Baseline

**PACKAGE:** IG-07 / Slice 2E
**BASELINE REVISION:** `88773e7` (exact pre-inversion HEAD)
**STATUS:** E1 evidence recorded; E2 implementation is bounded by this matrix.

## Objective

`scripts/task_model.py` içindeki deterministic task contract'ı
`brain_eleven/runtime/task.py` canonical package surface'ine çevirmek. E2
sırasında davranış, JSON contract, exception identity, registry read-only
semantics ve evaluation corpus değişmeyecek.

## Canonical public export list

`brain_eleven.runtime.task` canonical implementation'da aşağıdaki isimleri
export eder:

### Authority and schema constants

```text
ProjectRegistry
ProjectRegistryError
TASK_SCHEMA_VERSION
TASK_ID_PREFIX
TASK_LIFECYCLES
PROJECT_RESOLUTION_STATUSES
INTENTS
OPERATIONS
RISK_LEVELS
REQUESTED_OUTPUTS
EVIDENCE_SOURCES
MAX_REQUEST_CHARS
```

### Errors and models

```text
TaskValidationError
TaskProjectResolutionError
Evidence
ProjectResolution
TaskEnvelope
TaskAnalyzer
```

### Functions and CLI

```text
utc_now
new_task_id
resolve_project
validate_task
render_task_json
main
```

The implementation also retains the existing private rule tables and helper
functions internally. The adapter may expose them as compatibility aliases,
but they are not new public API or a tuning surface.

## Legacy name matrix

| Historical access | Canonical source | Adapter obligation |
|---|---|---|
| `scripts.task_model.TaskAnalyzer` | `brain_eleven.runtime.task.TaskAnalyzer` | Same object |
| `scripts.task_model.TaskEnvelope` | `brain_eleven.runtime.task.TaskEnvelope` | Same object |
| `scripts.task_model.Evidence` | `brain_eleven.runtime.task.Evidence` | Same object |
| `scripts.task_model.ProjectResolution` | `brain_eleven.runtime.task.ProjectResolution` | Same object |
| `scripts.task_model.TaskValidationError` | canonical error | Same object |
| `scripts.task_model.TaskProjectResolutionError` | canonical error | Same object |
| `scripts.task_model.ProjectRegistry` | `brain_eleven.projects.registry.ProjectRegistry` | Re-export unchanged |
| `scripts.task_model.ProjectRegistryError` | `brain_eleven.projects.registry.ProjectRegistryError` | Re-export unchanged |
| `scripts.task_model.TASK_*` / `INTENTS` / `OPERATIONS` / `RISK_LEVELS` / `REQUESTED_OUTPUTS` / `EVIDENCE_SOURCES` | canonical constants | Same object/value |
| `scripts.task_model.utc_now` / `new_task_id` / `resolve_project` | canonical functions | Same object |
| `scripts.task_model.validate_task` | canonical function | Same object |
| `scripts.task_model.render_task_json` | canonical function | Same object |
| `scripts.task_model.main` | canonical CLI | Same object; `__main__` delegates |
| bare `task_model.<name>` | adapter compatibility alias | Same object as package and `scripts.task_model` |
| `task_state_context.py` imports | `scripts.task_model` then bare fallback | Source file unchanged |
| `authority/serialization.py` local import | `scripts.task_model.TaskEnvelope` | Source file unchanged |
| `evals/task_state_eval.py` import | `scripts.task_model.TaskAnalyzer` | Source file unchanged |

The adapter must preserve `sys.modules['task_model']` and
`sys.modules['scripts.task_model']` compatibility behavior without defining a
second class, rule table, validator, or persistence path.

## Baseline artifacts

Generated at exact revision `88773e7` with the existing evaluator and no
production changes:

| Suite | Artifact | Gate | Task cases | State cases |
|---|---|---|---:|---:|
| smoke | `evals/reports/ig07-slice2e/before-smoke.json` | pass | 20 | 20 |
| public | `evals/reports/ig07-slice2e/before-public.json` | pass | 24 | 24 |
| holdout | `evals/reports/ig07-slice2e/before-holdout.json` | pass | 4 | 4 |

Baseline commands:

```text
python -m evals.task_state_eval --suite smoke --report evals/reports/ig07-slice2e/before-smoke.json
python -m evals.task_state_eval --suite public --report evals/reports/ig07-slice2e/before-public.json
python -m evals.task_state_eval --suite holdout --report evals/reports/ig07-slice2e/before-holdout.json
```

All three reports returned `gate=pass`, provider `task_state_v1`, schema
version `1`.

The migration-focused pre-E2 suite was run unchanged:

```text
tests/test_task_model.py
tests/test_task_state_context.py
tests/test_context_router.py
tests/test_context_engine_operational_surfaces.py
tests/test_context_compiler_v2.py
tests/test_context_compiler_v2_hardening.py
tests/test_authority_resolver.py
tests/test_task_state_eval.py
tests/test_pre12_project_caller_migration.py
tests/test_pre12_memory_state_caller_migration.py
```

Result: **107 passed in 5.70s**.

## E2 stop conditions

E2 stops and reports `RETHINK / defer` if any of these cannot be preserved:

1. package, `scripts.task_model`, and bare `task_model` identity;
2. `task_state_context.py` byte-for-byte unchanged;
3. TaskEnvelope JSON keys, field order, schema and exception identity;
4. deterministic rule tables and analyzer outputs;
5. unchanged authority serialization and holdout evaluation artifacts.

No tuning, label edits, fixture edits, threshold edits, or temporary
compatibility code in `task_state_context.py` is permitted.
