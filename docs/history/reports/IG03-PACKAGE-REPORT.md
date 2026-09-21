# IG-03 Package Report — Semantic Extraction

**PACKAGE:** IG-03  
**REVISION:** `092bec9741d2d123adfb18c2ebb2b225e7fb17b8` (exact implementation/test head producing the evidence below; documentation closure is recorded separately)
**STATUS:** ACCEPTED / SHIPPED

## OBJECTIVE

Freeze a proposal-only semantic extraction boundary behind deterministic safety
prefiltering, strict IG01-A proposition validation and content-free benchmark
evidence. No canonical writer, lifecycle mutation, retrieval path or V2
runtime path was changed.

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

The final acceptance correction is limited to `evals/ig03/benchmark.py` and
its focused test. It canonicalizes CRLF/LF before hashing public JSONL splits,
so an unchanged corpus has the same manifest fingerprint on Windows and Linux.

## ROOT CAUSES ADDRESSED

* Regex-only extraction had no frozen semantic proposition boundary.
* Provider output could not be measured without a strict, authority-safe
  schema and deterministic validation.
* Prefilter decisions, source role, project scope and evidence references were
  not independently protected from model output.
* Benchmark corpus provenance, unavailable-provider semantics, ECE aggregation
  and provider revision evidence were under-specified.
* Windows checkout line endings made immutable JSONL fingerprints fail despite
  unchanged logical corpus content.

## TESTS ADDED

Focused tests cover secret/quote/question/hypothetical prefiltering, strict
schema and nested-field rejection, source-role authority, direct proposition
revalidation, unavailable providers, manifest provenance, exact SHA binding,
strict review hashes, unavailable metric applicability, IG01-C ten-bin ECE and
line-ending-invariant public split fingerprints.

## TESTS EXECUTED

All local commands below were run from the exact revision shown above:

* focused IG-03 suite: **18 passed**;
* non-integration regression: **741 passed, 3 skipped, 42 deselected**;
* integration/graduation regression: **42 passed, 743 deselected**;
* `compileall` for `brain_eleven`, `evals` and `tests`: **PASS**;
* `git diff --check`: **PASS**;
* critical flake8 was executed in CI; local bundled runtime did not include the
  flake8 module;
* extraction bandit scan: **0 findings** in the prior exact implementation
  evidence; final CI security gates are recorded below.

## QUALITY METRICS BEFORE / AFTER

Before, IG-03 had no semantic provider boundary or valid provider benchmark.
After, the deterministic control is measured on both allowed public splits;
the local Qwen and stronger provider slots are explicit
`SEMANTIC_UNAVAILABLE`, with all quality metrics `not_applicable` and zero
applicable cases. The DEV control reports 49 extraction cases (44 measured,
5 filtered); VALIDATION reports 25 cases (23 measured, 2 filtered). No
HOLDOUT case is opened. The semantic provider remains proposal-only, so no
production quality claim is made for an unavailable model.

## SAFETY METRICS

The focused, benchmark and exact-head CI runs recorded zero authority,
canonical-write, assistant-as-user, forbidden-content or scope safety events.
Validation security gates passed: Bandit, secret detection, dependency audit
and Docker image scan. Phase 20 remains `FROZEN / LOCKED`; V2 remains
`SHADOW`.

## REMOTE CI

* Validation run [34373232663](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34373232663), head `092bec9741d2d123adfb18c2ebb2b225e7fb17b8`: **SUCCESS**.
  Ubuntu and Windows unit, integration, coverage, context privacy, evaluation
  smoke, IG01-B/C/D/E, router/authority/compiler smoke and security jobs passed.
  Push-only public/evidence jobs were skipped by their declared branch policy.
* PRE-13 runtime run [34373232686](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34373232686), same head: Ubuntu and Windows runtime jobs **PASS**. Its separate historical quality job remains **FAIL** on the frozen PRE-13 quality corpus; this failure is retained visibly and is not relabeled as an IG-03 semantic result.

## KNOWN LIMITATIONS

No local Qwen-class or stronger semantic extraction runtime is configured, so
semantic quality improvement over the deterministic control is not measured.
The implementation remains proposal-only and is not connected to active
capture, truth, retrieval or runtime delivery. The historical PRE-13 quality
gate remains below its old threshold and is an upstream intelligence
remediation item.

## OPEN FAILURES

No IG-03 P0 or unexplained critical failure remains. The historical PRE-13
quality failure in runtime run `34373232686` remains open by design and must be
addressed by later evaluation/intelligence packages; thresholds were not
lowered and the failure was not hidden.

## INDEPENDENT REVIEW

Fresh independent read-only review of the final documentation closure
returned **SHIP, 9/10** at exact documentation head
`00947a2e6b2664d8b2e6f1af3f394ca6460f6793`. The reviewer verified the exact
implementation/test head `092bec9741d2d123adfb18c2ebb2b225e7fb17b8`, Windows
fingerprint correction, Validation/runtime evidence, package boundary and
Phase 20/V2 locks. P0/P1/P2 findings: none.

## SCORE BEFORE / AFTER

* IG-03 extraction foundation: **4/10 → 9/10** for contract and safety
  readiness;
* measured semantic provider quality: **not graduated** because optional
  providers are unavailable.

## VERDICT

**SHIP** — exact implementation/test evidence, exact-head Validation CI and
independent read-only review all pass. The historical PRE-13 quality failure
remains visible as a later intelligence-quality item. IG-02 may begin its own
bounded audit/contract sequence in the mandated IG-03 → IG-02 → IG-04 order; Phase 20 remains `FROZEN / LOCKED`.
