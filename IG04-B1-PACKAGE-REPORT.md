# IG-04 B1 Package Report

**PACKAGE:** IG-04 B1 — Human-Approved Retrieval
**REVISION:** `4edd4df`
**OBJECTIVE:** Add the bounded human-approval boundary to the existing V1
capture/review path without promoting V2, changing ranking, or opening Phase
20.

## FILES CHANGED

`brain_eleven/runtime/review.py`, `worker.py`, `storage.py`, `context.py`,
`service.py`, `model.py`, `__main__.py`, the review UI reason map, the approved
`IG04-B1-CONTRACT.md`, `PROJECT-STATUS.md`, `NEXT.md`,
`DOCUMENTATION-AUTHORITY.md`, and `tests/test_ig04_b1_human_approval.py`.

## ROOT CAUSES ADDRESSED

* Automatic CANARY/ACTIVE capture could write canonical memory without a
  package-level human approval boundary.
* Review terminal records did not retain a content-free fingerprint for
  rejection replay suppression.
* Duplicate deliveries with different candidate IDs could create duplicate
  review records.
* Native runtime imports still relied on a scripts-path side effect in review
  and optional model paths.

## TESTS ADDED

* B1 capture holds a candidate in `PENDING` and keeps it out of SessionStart
  context until explicit acceptance.
* Review API lists a scoped pending candidate.
* Accept is idempotent and produces one canonical effect.
* Reject retains bounded audit metadata and suppresses the same fingerprint on
  replay without retaining candidate text.
* The B1 switch defaults off and is explicitly toggleable.

## TESTS EXECUTED

* `.venv\\Scripts\\python.exe -m pytest tests/test_ig04_b1_human_approval.py -q` —
  **3 passed**.
* `.venv\\Scripts\\python.exe -m pytest tests -q` — **851 passed, 2 warnings**.
* Critical flake8 (`E9,F63,F7,F82`) on changed Python files — **pass**.
* `compileall` for `brain_eleven` and `scripts` — **pass**.
* `git diff --check` — **pass**.

## QUALITY METRICS BEFORE / AFTER

The B1 implementation does not claim retrieval-quality improvement. The V1
ranking baseline is unchanged; only the eligibility boundary is gated. No
precision, recall, or task-understanding score is promoted by this package.

## SAFETY METRICS

Pending, rejected and expired review records are not canonical memory and are
not eligible for V1 bootstrap retrieval. Candidate text is removed from
terminal review records; fingerprint, project, candidate identity, evidence
references and reason remain for bounded audit/replay suppression. Canonical
acceptance still passes the existing safety, lifecycle, CAS and receipt path.

## KNOWN LIMITATIONS

The B1 switch is disabled by default and has not been promoted for daily use.
Remote exact-head CI, real Claude/Codex native-client trust evidence and an
independent read-only review have not yet been recorded for this revision.

## OPEN FAILURES

* Independent read-only reviewer verdict is pending.
* Remote package CI and runtime evidence for the exact implementation revision
  are pending.
* Native client trust verification remains a separate operational gate.

## INDEPENDENT REVIEW

**NOT RUN.** Implementer self-review is not independent evidence under the
B1 contract.

## SCORE BEFORE / AFTER

No graduation score change. Capture/runtime and safety behavior is covered by
focused evidence; intelligence quality remains at the previously measured
baseline.

## VERDICT

**FIX-FIRST / NOT ACCEPTED** — implementation and local evidence are present,
but B1 remains open until the remote, native and independent-review gates are
closed. V2 remains `SHADOW`; Phase 20 remains `FROZEN / LOCKED`.
