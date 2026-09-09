# IG-02 Package Report — Autonomous Capture Closure

**PACKAGE:** IG-02  
**REVISION:** `3404a9b2e3e5681fe3aca38cb6597e28bf95d20d` (exact implementation/test head; documentation closure is recorded separately)
**STATUS:** IMPLEMENTATION COMPLETE / ACCEPTANCE PENDING

## OBJECTIVE

Close the Claude/Codex capture hand-off from bounded native event through the
durable queue, leased worker and evidence reader to a verified canonical effect
or durable review effect. A queue job may enter `COMMITTED` only after a
matching content-free `EFFECT_VERIFIED` receipt has been durably written.

## FILES CHANGED

* `brain_eleven/runtime/worker.py`
* `scripts/capture_queue.py`
* `evals/ig01e/audit.py`
* `tests/test_capture_queue.py`
* `tests/test_ig02_capture_closure.py`
* `IG02-AUTONOMOUS-CAPTURE-CONTRACT.md`
* `IG02-NATIVE-SMOKE-EVIDENCE.md`
* `IG02-PACKAGE-REPORT.md`
* `PROJECT-STATUS.md`
* `RUNTIME-DATAFLOW.md`
* `DOCUMENTATION-AUTHORITY.md`

## ROOT CAUSES ADDRESSED

* Worker acknowledgement previously trusted a processed return value without a
  durable proof of canonical or review effect.
* A crash after canonical write and before queue acknowledgement could advance
  the cursor before an effect receipt and later report a false successful tail.
* Replay receipts did not bind project/checkpoint identity or verify surviving
  canonical effects.
* Review persistence failures were not promoted to bounded retryable errors.
* Missing transcripts raised an unbounded filesystem error at enqueue time.
* Queue job identifiers accepted path-like values when reading corrupt jobs and
  did not validate job/event idempotency correspondence.
* IG01-E documentation auditing assumed IG-01 would remain the latest closed
  package after later IG packages shipped.

## TESTS ADDED

Focused IG-02 coverage proves receipt-gated acknowledgement, multi-chunk
receipt-write crash recovery, surviving-effect tamper rejection, replay after a
crash before queue acknowledgement, corrupt/foreign receipt retry, crash before
canonical write, Claude and Codex worker golden paths, lock timeout,
deleted/corrupt transcript dead-lettering, invalid project handling, conflict
retry and queue identity path/semantic containment. Existing runtime tests
cover duplicate delivery, lease recovery, rewrites, service draining and review
recovery.

## TESTS EXECUTED

All local results below were run against the exact implementation revision
shown above (temporary test directories were outside the repository or removed
afterward):

* IG-02 + queue + event/evidence + PRE-13 focused suite: **102 passed**;
* non-integration regression excluding the two IG01-B/E files whose local
  private-fixture lifecycle requires separate cleanup: **747 passed, 3 skipped,
  42 deselected**;
* IG01-B corpus suite: **6 passed**;
* IG01-E audit suite: **7 passed**;
* integration/graduation regression: **42 passed, 763 deselected**;
* `compileall` for `brain_eleven`, `evals` and `tests`: **PASS**;
* `git diff --check`: **PASS**;
* bundled local runtime has no `flake8` or `bandit` modules; those gates ran in
  exact-head CI below.

## REMOTE CI

* Validation run [34381739251](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34381739251), head `3404a9b2e3e5681fe3aca38cb6597e28bf95d20d`: **SUCCESS**. Ubuntu/Windows unit, integration, coverage, context privacy, evaluation smoke, IG01-B/C/D/E, router/authority/compiler smoke, Bandit, secret detection, dependency security, Docker image security and Phase 14 evidence passed; master-only public/evidence suites were skipped by their declared branch policy.
* PRE-13 runtime run [34381739315](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34381739315), same head: overall **FAILURE** only because the historical `quality` job failed; Ubuntu and Windows runtime jobs **PASS**.
* Previous implementation run [34378278695](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34378278695) is retained as historical evidence; it passed Validation before the crash-window fixes.

## QUALITY METRICS BEFORE / AFTER

Before, queue completion could advance the cursor before a durable effect proof
and replay trusted weak operation metadata. After, receipt durability precedes
checkpoint advancement, multi-chunk cursors are receipt-bound, replay verifies
operation identity and surviving canonical effects, and queue identity is
semantic and fail-closed. This package measures capture reliability and
truth-boundary evidence; it makes no extraction or retrieval quality claim.

## SAFETY METRICS

Focused tests retain zero duplicate canonical effects, zero cross-project
capture, zero raw-content receipt fields, zero false completions after receipt
or canonical tampering, and zero silent acknowledgement paths. Queue
identifiers are restricted to the generated `cap_` plus 32-hex form. Phase 20
remains **FROZEN / LOCKED** and V2 remains **SHADOW**.

## NATIVE CLIENT TRUST

The real Claude and Codex executables invoked isolated native hook entry points
without opening a visible window. Claude stopped at missing API authentication;
Codex stopped after network retries, so neither run had a client-owned
transcript to enqueue. This is an explicit bounded exception, recorded without
content in [IG02-NATIVE-SMOKE-EVIDENCE.md](IG02-NATIVE-SMOKE-EVIDENCE.md).
The launcher golden test and both client transcript-shape runtime tests verify
queue delivery, receipt creation and canonical verification independently.

## KNOWN LIMITATIONS

Real-client authenticated autonomous capture is not verified in this local
environment. The optional semantic provider remains unavailable and the
historical PRE-13 quality failure remains an intelligence-quality item for
later packages. Receipt verification persists no memory content; it proves the
exact operation receipt, request identity, decision correspondence and
surviving effect IDs.

## OPEN FAILURES

No new IG-02 P0 or unexplained local runtime failure is open. The PRE-13
historical quality failure is intentionally retained. Exact-head remote CI and
independent read-only re-review are pending; until both return accepted results,
IG-02 is not accepted and IG-04 cannot start.

## INDEPENDENT REVIEW

The prior read-only review returned `FIX-FIRST` at 5/10 for the crash window
and receipt/identity gaps. A fresh read-only re-review is required for exact
head `3404a9b2e3e5681fe3aca38cb6597e28bf95d20d` after remote CI completes.
Self-review is not counted as independent.

## SCORE BEFORE / AFTER

* Capture runtime infrastructure: **7.5/10 → pending reviewer score**;
* Persistence/concurrency and scope safety are unchanged by this package;
* Extraction, correction, retrieval, context and daily-use scores are not
  increased by IG-02.

## VERDICT

**FIX-FIRST / NOT ACCEPTED** pending independent read-only review. If the
reviewer returns `SHIP`, the documentation closure will change this verdict to
`SHIP`; if it returns `FIX-FIRST` or `RETHINK`, IG-02 remains open and no IG-04
implementation begins.
