# IG-02 Package Report — Autonomous Capture Closure

**PACKAGE:** IG-02  
**REVISION:** `29d4e28a50625625406b1795fd4296238a892520` (exact implementation/test head; documentation closure is recorded separately)  
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
* A crash after canonical write and before queue acknowledgement could replay
  expensive processing without an effect receipt.
* Review persistence failures were not promoted to bounded retryable errors.
* Missing transcripts raised an unbounded filesystem error at enqueue time.
* Queue job identifiers accepted path-like values when reading corrupt jobs.
* IG01-E documentation auditing assumed IG-01 would remain the latest closed
  package after later IG packages shipped.

## TESTS ADDED

Focused IG-02 coverage proves receipt-gated acknowledgement, replay after a
crash before queue acknowledgement, corrupt receipt retry, crash before
canonical write, the native launcher golden path, missing transcript handling,
and queue job identity path containment. Existing runtime tests cover both
Claude and Codex transcript shapes, duplicate delivery, lease recovery,
rewrites, lock/CAS failures, service draining and review recovery.

## TESTS EXECUTED

All local results below were run against the exact implementation revision
shown above (temporary test directories were outside the repository or removed
afterward):

* IG-02 + queue + event/evidence + PRE-13 focused suite: **90 passed**;
* non-integration regression excluding the two IG01-B/E files whose local
  private-fixture lifecycle requires separate cleanup: **735 passed, 3 skipped,
  42 deselected**;
* IG01-B corpus suite: **6 passed**;
* IG01-E audit suite: **7 passed**;
* integration/graduation regression: **42 passed, 751 deselected**;
* `compileall` for `brain_eleven`, `evals` and `tests`: **PASS**;
* `git diff --check`: **PASS**;
* bundled local runtime has no `flake8` or `bandit` modules; those gates ran in
  exact-head CI below.

## REMOTE CI

* Validation run [34378278695](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34378278695), head `29d4e28a50625625406b1795fd4296238a892520`: **SUCCESS**. Ubuntu/Windows unit, integration, coverage, context privacy, evaluation smoke, IG01-B/C/D/E, router/authority/compiler smoke, Bandit, secret detection, dependency security and Docker image security passed. Master-only public/evidence jobs were skipped by their declared branch policy.
* PRE-13 runtime run [34378278696](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34378278696), same head: Ubuntu and Windows runtime jobs **PASS** with coverage and Bandit; its separate historical holdout quality job is **FAIL** and remains visible by design.

## QUALITY METRICS BEFORE / AFTER

Before, queue completion did not have a durable effect proof. After, every
successful worker result writes a schema-versioned content-free receipt before
the queue commit, and replay consumes that receipt without creating a second
canonical effect. This package measures capture reliability and truth-boundary
evidence; it makes no extraction or retrieval quality claim.

## SAFETY METRICS

Focused and exact-head CI tests retain zero duplicate canonical effects, zero
cross-project capture, zero raw-content receipt fields and zero silent
acknowledgement paths. Queue identifiers are restricted to the generated
`cap_` plus 32-hex form. Phase 20 remains **FROZEN / LOCKED** and V2 remains
**SHADOW**.

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
later packages. Receipt verification currently proves the canonical operation
receipt and successful decision list; it does not persist memory content.

## OPEN FAILURES

No new IG-02 P0 or unexplained runtime failure is open. The PRE-13 historical
quality failure is intentionally retained. Independent read-only review is
still pending; until it returns `SHIP`, IG-02 is not accepted and IG-04 cannot
start.

## INDEPENDENT REVIEW

Fresh read-only review was requested for exact implementation head
`29d4e28a50625625406b1795fd4296238a892520`; result will be recorded in the
documentation-closure commit. Self-review is not counted as independent.

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
