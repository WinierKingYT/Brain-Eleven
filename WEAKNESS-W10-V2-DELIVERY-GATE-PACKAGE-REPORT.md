# W-10 — V2 Shadow Delivery Gate Package Report

**PACKAGE:** W-10  
**REVISION:** `29aa519b60b09e16d92d709dee70cb9529b8cc81`  
**OBJECTIVE:** Restore the non-injecting V2 `SHADOW` boundary and make the
model-facing provider explicit.

**PROGRAM STATE:** Phase 20 `FROZEN / LOCKED`; V2 product status `SHADOW`.

## Files changed

- `brain_eleven/runtime/context.py`
- `brain_eleven/runtime/launcher.py`
- `tests/test_w10_v2_delivery_gate.py`

The historical `compile_task` name remains the V2 compatibility API for the
offline PRE-13 evaluator. Native normal-turn delivery calls the named
`compile_task_v1` adapter. No evaluation corpus, holdout label, canonical
store, retrieval weight, or Phase 20 file changed.

## Root causes addressed

- Normal `V1_LEGACY` turns were rendered by `ContextCompilerV2` and could be
  returned as `provider: V1`.
- The native launcher inferred delivery from a non-empty context instead of
  checking an explicit approved-delivery marker and provider.
- The legacy public compiler projection reads unscoped Companion files; the
  normal V1 adapter now uses only `_rank_memories`, `_resolve_current_state`,
  and `_generate_context_block` with empty related/unscoped note inputs.

## Implementation

- Added the project-scoped `compile_task_v1` adapter with memory/state
  revision revalidation, scope filtering, B1 approval filtering, secret and
  capture-safety checks, and bounded token handling.
- Kept `compile_task` / `compile_task_v2_shadow` available only as the
  historical diagnostic/evaluation V2 surface; native `compile_context`
  normal turns do not call it.
- In `SHADOW`, normal UserPromptSubmit results contain no model-facing text.
  In `CANARY` and `ACTIVE`, delivery is approved only for `V1` or the existing
  `W06B_TASK_AWARE` provider while the product-level V2 status remains
  `SHADOW`.
- The launcher requires `delivery_approved == true`, an allowed provider, an
  explicit `delivered == true`, and non-empty context for every current
  service response. Missing approval/provider metadata fails closed.
- Normal-turn V1 preserves the existing bounded state identity markers needed
  by the task/state runtime; SessionStart's established V1 bootstrap rendering
  remains unchanged.

## Tests added

`tests/test_w10_v2_delivery_gate.py` covers:

- Companion sentinel exclusion from V1 context and telemetry;
- project-scoped normal V1/bootstrap parity;
- proof that normal V1 does not invoke the V2 renderer;
- `SHADOW` no-delivery behavior;
- launcher rejection of V2 provider, missing approval, mismatched metadata,
  and missing delivery fields;
- explicit V1 delivery through the current service contract.

## Tests executed

- `python -m pytest tests/test_w10_v2_delivery_gate.py tests/test_ig00_bootstrap.py tests/test_w06b_task_aware.py tests/test_pre13_runtime.py -q` — **82 passed, 2 warnings**
- `python -m pytest tests -q` — **1177 passed, 2 warnings** at this exact revision
- `python -m flake8 --select=E9,F63,F7,F82 brain_eleven/runtime/context.py brain_eleven/runtime/launcher.py tests/test_w10_v2_delivery_gate.py tests/test_ig00_bootstrap.py tests/test_pre13_runtime.py` — **passed**
- `python -m compileall -q brain_eleven/runtime/context.py brain_eleven/runtime/launcher.py tests/test_w10_v2_delivery_gate.py tests/test_ig00_bootstrap.py tests/test_pre13_runtime.py` — **passed**
- `git diff --check` — **passed**

All commands used the repository `.venv` interpreter. The full suite was run
at the exact implementation revision above.

## Quality metrics before / after

| Measure | Before W-10 | After W-10 |
| --- | --- | --- |
| Normal V1_LEGACY model-facing source | V2 renderer relabeled V1 | Project-scoped V1 adapter |
| V2 text delivered while product is SHADOW | Possible | Blocked by provider and approval gate |
| Normal SHADOW context delivery | Non-empty internal result could be exposed by a caller | Empty context, `delivered=false` |
| V1/bootstrap parity on focused fixture | Unspecified | Byte-equal context |
| Full regression | Baseline prior to package | 1177 passed |

## Safety metrics

- Companion raw text in normal context: **0** in focused sentinel test.
- Companion raw text in telemetry: **0** in focused sentinel test.
- V2 provider delivered through launcher: **0** in mismatch test.
- Missing approval/provider metadata delivered through current gate: **0**.
- Project/state snapshot revalidation: preserved and covered by existing full
  runtime suite.
- Canonical writes or model-output-to-truth paths introduced: **0**.

## Known limitations

- This package does not promote V2 or compute a new V2 comparison stream; V2
  remains `SHADOW` by contract.
- Real Claude/Codex executable trust and native-client dogfood remain separate
  W-07B acceptance gates and were not claimed here.
- The normal-turn V1 adapter intentionally preserves the legacy state-record
  identity section required by the existing runtime suite; it does not read
  unscoped Companion files.

## Open failures

- No W-10 test or full-suite failure remains.
- The first independent review found a P1 metadata bypass; it was removed in
  `29aa519`, with missing metadata now rejected and the focused/full suites
  rerun. Independent read-only re-review is still required.

## Independent review

**REVIEW PENDING after hardening.** The implementer does not self-declare
`SHIP`.

## Score before / after

- V2 production readiness: **4.0 / 10 before**; post-implementation score is
  **not promoted before independent review**.
- Context compilation: **6.8 / 10 before**; no graduation score increase is
  claimed before review.

## Verdict

**REVIEW PENDING**
