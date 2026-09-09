# IG-02 Package Report — Autonomous Capture Closure

**PACKAGE:** IG-02  
**REVISION:** `72a8475a8d01d50a632f25c23f1fc8a507053c42` (exact implementation/test head; documentation closure is recorded separately)
**STATUS:** SHIPPED / ACCEPTED

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
* Replay receipt references were not fully bound to project-scoped memory,
  state-record provenance, review identity, or effect-ID correspondence.

## TESTS ADDED

Focused IG-02 coverage proves receipt-gated acknowledgement, multi-chunk
receipt-write crash recovery, surviving-effect tamper rejection, replay after a
crash before queue acknowledgement, corrupt/foreign receipt retry, crash before
canonical write, Claude and Codex worker golden paths, StateStore golden and
lifecycle replay, lock timeout, deleted/corrupt transcript dead-lettering,
invalid project handling, conflict retry, cross-project memory rejection,
state/review provenance binding, effect-list tamper rejection and queue
identity path/semantic containment. Existing runtime tests cover duplicate
delivery, lease recovery, rewrites, service draining and review recovery.

## TESTS EXECUTED

All local results below were run against the exact implementation revision
shown above (temporary test directories were outside the repository or removed
afterward):

* IG-02 + queue focused suite at the exact head: **39 passed**;
* non-integration regression: **774 passed, 3 skipped, 42 deselected**;
* integration/graduation regression: **42 passed, 777 deselected**;
* `compileall` for `brain_eleven`, `evals` and `tests`: **PASS**;
* `git diff --check`: **PASS**;
* bundled local runtime has no `flake8` or `bandit` modules; those gates ran in
  exact-head CI below.

## REMOTE CI

* Validation run [34387725841](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34387725841), head `72a8475a8d01d50a632f25c23f1fc8a507053c42`: **SUCCESS**. Unit Linux/Windows, integration, privacy, evaluation, coverage, Bandit, secrets, dependency, Docker and smoke checks passed.
* PRE-13 runtime run [34387725837](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34387725837), same head: runtime Ubuntu/Windows and coverage **PASS**; the historical holdout quality job is **FAILURE** and remains visible for later intelligence work.
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
exact operation receipt, request identity, project/evidence binding, decision
correspondence and surviving effect IDs.

## OPEN FAILURES

No new IG-02 P0/P1 or unexplained local runtime failure is open. The PRE-13
historical quality failure is intentionally retained for later intelligence
work. IG-02 acceptance is closed; IG-04 remains unopened by the program order.

## INDEPENDENT REVIEW

The prior read-only reviews returned `FIX-FIRST` while identifying and closing
crash-window, canonical-effect, memory/state/review identity and privacy-format
gaps. The final independent read-only re-review is bound to exact head
`72a8475a8d01d50a632f25c23f1fc8a507053c42` and returned **SHIP / 9/10**;
self-review is not counted as independent.

## SCORE BEFORE / AFTER

* Capture runtime infrastructure: **7.5/10 → 9/10**;
* Persistence/concurrency and scope safety are unchanged by this package;
* Extraction, correction, retrieval, context and daily-use scores are not
  increased by IG-02.

## VERDICT

**SHIP** — exact-head local and remote evidence passed, and the independent
read-only reviewer returned `SHIP / 9/10`. Phase 20 remains FROZEN / LOCKED and
IG-04 is not opened in this execution.
