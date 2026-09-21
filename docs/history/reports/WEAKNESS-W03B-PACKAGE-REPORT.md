# W-03B Package Report — Transcript Ownership and Session Provenance

**PACKAGE:** W-03B
**REVISION:** `f1d889620e359e6ab54ae81de106b983c412c562`
**OBJECTIVE:** Prevent a transcript inside a trusted client root from being
  attributed to the wrong native session or project before evidence/canonical
  processing.

## FILES CHANGED

- `brain_eleven/runtime/ownership.py`
- `brain_eleven/runtime/evidence.py`
- `brain_eleven/runtime/worker.py`
- `scripts/capture_queue.py`
- `tests/test_w03b_transcript_ownership.py`
- ownership metadata updates in existing capture fixtures/tests

## ROOT CAUSES ADDRESSED

- Trusted-root confinement did not prove session/project ownership.
- Queue events store `client:sha256(raw_session_id)` but the native metadata
  binding was previously absent.
- A file could be replaced between ownership validation and evidence reading.
- Ownership failures followed the normal bounded retry path instead of an
  explicit terminal dead-letter path.

## TESTS ADDED

- Claude and Codex matching ownership/capture path.
- Foreign session and foreign project rejection before evidence persistence.
- Unknown metadata fail-closed and content-free diagnostics.
- Same-size transcript replacement detection using stable identity/content
  binding.
- Worker-level `TRANSCRIPT_CHANGED` preservation and zero-effect retry.
- Native fixture metadata/path binding for existing capture closure tests.

## TESTS EXECUTED

- Focused W-03B/capture/runtime suite: **127 passed, 2 warnings**.
- Critical flake8 (`E9,F63,F7,F82`): **PASS**.
- `compileall` on changed production modules: **PASS**.
- `git diff --check`: **PASS**.
- Full `pytest tests -q`: **1124 passed, 2 warnings**.
- The former W-06C0R1 scope-guard failures are closed by the separate
  W-06C0R1 scope-drift package; W-03B runtime behavior was unchanged.

## QUALITY METRICS BEFORE / AFTER

- Ownership proof: missing → strict Claude/Codex metadata and project binding.
- Cross-session leakage: reproduced P1 → focused test hard-zero.
- Cross-project leakage: unverified → focused test hard-zero.
- Same-size replacement: unguarded → `TRANSCRIPT_CHANGED` fail-closed.
- Missing locator: remains bounded retryable per W-04.

## SAFETY METRICS

- Foreign session/project canonical effects: **0** in focused tests.
- Unknown ownership evidence/canonical effects: **0**.
- Raw transcript content/full private path in ownership diagnostics: **0**.
- Canonical authority additions: **0**.

## KNOWN LIMITATIONS

- Native client adapters are intentionally strict. Unsupported future native
  transcript formats remain rejected until a reviewed contract revision adds
  metadata evidence.
- Scope verification is delegated to the independently shipped W-06C0R1
  scope-drift package; this package does not alter its evaluator boundary.

## OPEN FAILURES

- None observed at the exact review head.

## INDEPENDENT REVIEW

Contract: `SHIP` at `c3dcb10`.
Implementation review: **SHIP** at exact head `f1d8896`.

## SCORE BEFORE / AFTER

- Scope/fail-closed safety: 7.5 → 8.5.
- Capture runtime: 7.5 → 8.5.

## VERDICT

`SHIP` — implementation, full regression, and independent review are complete.
