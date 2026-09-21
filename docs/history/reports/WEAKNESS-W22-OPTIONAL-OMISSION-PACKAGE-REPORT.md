# W-22 — V2 Optional-Omission Package Report

**PACKAGE:** W-22
**REVISION:** `736c6c9a49b4698f3111eac0e71812fb2a514a51`
**OBJECTIVE:** Enforce `BudgetContract.allow_optional_omission` in the shadow
V2 planner and compiler without changing the default path.
**CONTRACT:** `WEAKNESS-W22-OPTIONAL-OMISSION-CONTRACT.md`, contract reviewed
**SHIP** at `9772458`.

## Files changed

- `context_compiler_v2/planner.py`
- `context_compiler_v2/compiler.py`
- `context_compiler_v2/serialization.py`
- `tests/test_w22_optional_omission.py`

## Root causes addressed

The budget contract serialized `allow_optional_omission`, but planner and final
rebalance logic ignored it. The V2 compiler could therefore report a valid
bundle after silently dropping optional context. The package now fails
visibly with `INSUFFICIENT_BUDGET` and the stable
`OPTIONAL_OMISSION_DISALLOWED` error when optional content cannot fit under a
false flag, while preserving mandatory-overflow precedence. Request decoding
also accepts the generated `usable_tokens` field only when it is an exact,
consistent integer.

## Tests added

- Planner-level false-flag omission detection and empty selection ledger.
- Profile-budget, profile-item-limit and optional-token overflow failures.
- Final-render overflow failure before optional removal.
- Mandatory-only final overflow precedence.
- All-fit false-flag parity with the default policy.
- True-flag profile omission compatibility.
- Budget request serialization round-trip and malformed derived-token
  rejection.
- Canonical source preservation and content-free failure output.

## Tests executed

- W-22 focused compiler/planner suite: **27 passed**
- Full suite at exact revision: **1338 passed, 4 skipped, 2 warnings**
- Critical flake8 (`E9,F63,F7,F82`): **PASS**
- compileall: **PASS**
- `git diff --check`: **PASS**

The two warnings are the existing FastAPI/Starlette dependency deprecation
warnings; no W-22 warning was introduced.

## Quality metrics before/after

- Before: `allow_optional_omission=False` was accepted and serialized but did
  not influence planner or final rebalance behavior.
- After: false disallowance is enforced at both planning and final-render
  boundaries with a visible, deterministic budget failure; true/default output
  remains compatible.

## Safety metrics

- Silent optional omission with the false flag: **0** in the profile, item,
  token and final-render matrix.
- Mandatory-overflow precedence regressions: **0**.
- Rendered context or private content in false-flag failure output: **0**.
- MemoryStore, StateStore, ProjectRegistry, authority or retrieval writes
  introduced: **0**.
- Malformed explicit `usable_tokens` values accepted: **0**.

## Known limitations

V2 remains **SHADOW**. This package does not change retrieval/ranking/provider
quality, promote V2, alter SessionStart/client delivery, or unlock Phase 20.
W-07B native trust/latency/dogfood remains open.

## Open failures

W-22 package failures: **none**. W-07B remains open outside this package.

## Independent review

Read-only implementation review at exact revision
`736c6c9a49b4698f3111eac0e71812fb2a514a51` returned **SHIP**. It independently
verified strict derived-token validation, mandatory-overflow precedence,
false-flag profile/item/final overflow behavior, true/default compatibility,
content-free failures, no writes and static gates. No P0, P1 or P2 findings
remain.

## Score before/after

- V2 runtime readiness: **6.5 → 6.8** (budget policy is now enforced and
  visible while promotion remains blocked).
- Context compilation: **6.8 → 7.0** (false-flag omission no longer silently
  succeeds).
- Retrieval quality and semantic retrieval correctness: unchanged.
- Other scorecard dimensions: unchanged.

## Verdict

**SHIP**
