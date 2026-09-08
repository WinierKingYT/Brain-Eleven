# IG-00 Package Report — Freeze & Baseline Closure

**PACKAGE:** IG-00 Freeze & Baseline
**REVISION:** `62871ff496b0cb46998aa9ea21dbcf9d5e03d27f`
**DATE:** 2026-09-08
**CONTRACT:** `IG00-FREEZE-BASELINE.md`
**DOCUMENTATION NOTE:** This report is a follow-up evidence record; the
revision above is the exact code/test revision used for the reported checks.

## OBJECTIVE

Close the Phase 20 freeze and baseline review without opening IG-01. Preserve
the immutable PRE-12 baseline, document the actual runtime paths, verify the
exact review revision, and keep every missing acceptance gate visible.

## FILES CHANGED

- `.github/workflows/test.yml` and `.github/workflows/runtime.yml`: include the
  review branch in push/PR filters so exact-head CI can run.
- `tests/test_context_router.py`: add fail-closed branch coverage required by
  the context-router coverage gate.
- `evals/intelligence_taxonomy.py`: clarify that the file is shared IG-00
  vocabulary only, with no evaluator or tuning implementation.
- IG-00 status/dataflow/report documents: revision-bound evidence and gate
  status only.

User-owned untracked files were not touched, staged or deleted.

## ROOT CAUSES ADDRESSED

- Exact-head evidence was previously bound to an older revision.
- Review-branch CI was not triggered by its branch filters.
- Context-router fail-closed branches were below the remote coverage threshold.
- The taxonomy artifact could be mistaken for IG-01 implementation; its scope is
  now explicit.

## TESTS ADDED

Four focused router tests cover graph candidate rehydration and scope,
malformed cache abstention, revision/state fail-closed behavior, and invalid
task rejection. No intelligence tuning or production retrieval change was
introduced.

## TESTS EXECUTED — EXACT REVISION

| Check | Result |
|---|---:|
| `pytest tests -m "not integration and not graduation"` | **680 passed**, 42 deselected, 2 warnings |
| `pytest tests -m "integration or graduation"` | **42 passed**, 680 deselected, 2 warnings |
| Requested IG-00 focused set | **179 passed**, 2 warnings |
| Taxonomy + router smoke | **27 passed** |
| Critical flake8 (`E9,F63,F7,F82`) | **PASS** |
| Bandit runtime (`brain_eleven/runtime`) | **PASS** |
| `git diff --check` | **PASS** |
| `pyproject.toml` parse | **PASS** |
| Import and compile sanity | **PASS** |

The local commands were run against `git rev-parse HEAD =
62871ff496b0cb46998aa9ea21dbcf9d5e03d27f` with hidden Windows execution.

## REMOTE CI EVIDENCE

All run and job results below report `head_sha =
62871ff496b0cb46998aa9ea21dbcf9d5e03d27f`.

- [Validation run 34266090585](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34266090585): **SUCCESS**.
  Ubuntu/Windows unit, integration, evaluation smoke, privacy, task/state,
  router/authority/compiler shadow smoke, coverage, secret, dependency, Docker
  and Bandit jobs passed. Public/evidence jobs conditioned on `master` were
  `SKIPPED`; skipped jobs are recorded as not applicable, never as passes.
- [PRE-13 runtime run 34266090649](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34266090649): overall **FAILURE** because its historical
  independent holdout quality job failed. Ubuntu and Windows runtime jobs both
  passed, including runtime coverage and Bandit. The retained holdout report
  measured runtime precision `0.1368`, required recall `0.2941`, with zero
  forbidden, project or lifecycle leakage; V1 precision was `0.1733` and
  required recall `0.7059`. This is an explicit PRE-13 intelligence-quality
  failure for later IG work, not a hidden infrastructure pass.

## NATIVE CLIENT TRUST / PRIVACY

Read-only inspection confirms the live Claude and Codex configuration contains
Brain-Eleven hook entries for the relevant lifecycle events. Isolated temporary
vault/config smoke runs exercised hidden native launchers, queue handoff,
receipts and canonical-effect verification without changing the live vault or
configuration. Raw prompts, transcripts, tokens and memory contents were not
stored in evidence. No authenticated live client turn was run; therefore live
client trust remains **BOUNDED / NOT VERIFIED**, rather than inferred from
configuration or isolated smoke.

## PACKAGE-BOUNDARY AUDIT

`evals/intelligence_taxonomy.py` is **IG-00 shared evaluation vocabulary**. Its
manifest, category validation and tests do not evaluate production output,
alter ranking weights, tune extraction, or open IG-01. The file is registered
as a current dataset/tool artifact; future evaluator implementation remains an
IG-01 deliverable.

## QUALITY METRICS BEFORE / AFTER

| Dimension | Before | After |
|---|---|---|
| Exact-head local validation | Older revision only | **62871ff: PASS** |
| Review-branch Validation CI | Not triggered | **PASS** |
| Runtime infrastructure | Partially evidenced | **Ubuntu/Windows PASS** |
| Historical PRE-13 quality | Failing | **Failure retained and visible** |
| Native client trust | Configuration-only | **Bounded; live trust unverified** |
| Independent review | Pending | **Pending** |

## SAFETY METRICS

- Wrong-project, forbidden and lifecycle leakage in the remote holdout report:
  `0`.
- Runtime Bandit, secret detection, dependency check and Docker scan: **PASS**.
- Live-vault/config mutation during native smoke: `0`.
- Synthetic semantic-vector fallback remains disabled in production.
- No model-to-canonical-write authority was introduced.

## KNOWN LIMITATIONS / OPEN FAILURES

1. No independent read-only reviewer is available in this execution context;
   self-review cannot satisfy the independent `SHIP` gate.
2. The GitHub connector rejected creation of the preferred master-targeted
   draft PR with HTTP 403. Exact-head push-triggered CI is available and passed
   the Validation workflow, but the draft PR itself was not created.
3. Historical PRE-13 holdout quality remains below its thresholds and must stay
   visible for IG-01 onward.
4. Conditional public/evidence jobs were skipped on the review branch and are
   not represented as successful evidence.

## INDEPENDENT REVIEW

**NOT AVAILABLE — no independent read-only reviewer was present.** The local
self-review below is explicitly non-independent and cannot change the verdict.

## SCORE BEFORE / AFTER

No intelligence score increase is claimed. IG-00 improves revision truthfulness,
CI topology evidence and validation coverage only; task understanding,
extraction, correction, retrieval quality and daily-use scores remain unchanged.

## VERDICT

**FIX-FIRST / NOT ACCEPTED**

The exact-head local and Validation evidence is complete, but IG-00 cannot be
accepted without an independent read-only `SHIP` review. Phase 20 remains
**FROZEN / LOCKED**, IG-01 remains **CLOSED**, and V2 remains **SHADOW**.
