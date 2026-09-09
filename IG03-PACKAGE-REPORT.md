# IG-03 Package Report — Semantic Extraction

**PACKAGE:** IG-03  
**REVISION:** `0200bf1f7b151103c059c45860b53894ebc07528`  
**STATUS:** Acceptance pending remote exact-head CI

## OBJECTIVE

Freeze a proposal-only semantic extraction boundary behind deterministic
safety prefiltering, strict IG01-A proposition validation and content-free
benchmark evidence. No canonical writer, lifecycle mutation, retrieval path or
V2 runtime path was changed.

## FILES CHANGED

* `brain_eleven/extraction/semantic.py`
* `brain_eleven/extraction/__init__.py`
* `evals/ig03/__init__.py`
* `evals/ig03/benchmark.py`
* `tests/test_ig03_semantic_extraction.py`
* `tests/test_ig03_benchmark.py`
* `IG03-SEMANTIC-EXTRACTION-AUDIT.md`
* `IG03-SEMANTIC-EXTRACTION-CONTRACT.md`
* `DOCUMENTATION-AUTHORITY.md`
* `PROJECT-STATUS.md`

## ROOT CAUSES ADDRESSED

* Regex-only extraction had no frozen semantic proposition boundary.
* Provider output could not be measured without a strict, authority-safe
  schema and deterministic validation.
* Prefilter decisions, source role, project scope and evidence references were
  not independently protected from model output.
* Benchmark corpus provenance, unavailable-provider semantics, ECE aggregation
  and provider revision evidence were under-specified.

## TESTS ADDED

Focused tests cover secret/quote/question/hypothetical prefiltering, strict
schema and nested-field rejection, source-role authority, direct proposition
revalidation, unavailable providers, manifest provenance, exact SHA binding,
strict review hashes, unavailable metric applicability and IG01-C ten-bin ECE.

## TESTS EXECUTED

All commands below were run with the exact revision shown above:

* focused IG-03 suite: **17 passed**;
* non-integration regression: **743 passed, 42 deselected**;
* integration/graduation regression: **42 passed, 743 deselected**;
* `compileall` for `brain_eleven`, `evals` and `tests`: **PASS**;
* `git diff --check`: **PASS**;
* critical flake8 (`E9,F63,F7,F82`): **0**;
* extraction bandit scan: **0 findings**.

## QUALITY METRICS BEFORE / AFTER

Before, IG-03 had no semantic provider boundary or valid provider benchmark.
After, the deterministic control is measured on both allowed public splits;
the local Qwen and stronger provider slots are explicit
`SEMANTIC_UNAVAILABLE`, with all quality metrics `not_applicable` and zero
applicable cases. The DEV control reports 49 extraction cases (44 measured,
5 filtered); VALIDATION reports 25 cases (23 measured, 2 filtered). No
HOLDOUT case is opened.

## SAFETY METRICS

The focused and benchmark runs recorded zero authority, canonical-write,
assistant-as-user, forbidden-content or scope safety events. Phase 20 remains
`FROZEN / LOCKED`; V2 remains `SHADOW`.

## KNOWN LIMITATIONS

No local Qwen-class or stronger semantic extraction runtime is configured, so
semantic quality improvement over the deterministic control is not measured.
The implementation remains proposal-only and is not connected to active
capture, truth, retrieval or runtime delivery.

## OPEN FAILURES

The required remote exact-head CI artifact has not been produced for branch
`ig/03-semantic-extraction`. A previous push attempt was rejected by the
automatic review because it would send repository source to the GitHub remote.
Until that operational gate is authorized and completed, this package cannot
be accepted as closed.

## INDEPENDENT REVIEW

Independent read-only review at the exact revision returned **SHIP, 9/10**;
all prior P1/P2 findings were verified closed. The reviewer explicitly left
remote exact-head CI as the remaining operational exit-gate item.

## SCORE BEFORE / AFTER

* IG-03 extraction foundation: **4/10 → 9/10** for contract and safety
  readiness;
* measured semantic provider quality: **not graduated** because optional
  providers are unavailable.

## VERDICT

**FIX-FIRST / NOT ACCEPTED** — implementation and local evidence pass, but
remote exact-head CI evidence is still required. IG-02 must not begin until
the missing gate is closed and a final package verdict is recorded.
