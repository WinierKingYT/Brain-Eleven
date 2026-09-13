# W-03B Package Report — Transcript Ownership and Session Provenance

**PACKAGE:** W-03B
**REVISION:** `42f573728de5f711fd982fda9bfc079735d0aae6`
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

- Focused W-03B/capture/runtime suite: **132 passed, 2 warnings**.
- Critical flake8 (`E9,F63,F7,F82`): **PASS**.
- `compileall` on changed production modules: **PASS**.
- `git diff --check`: **PASS**.
- Full `pytest tests -q`: **1116 passed, 2 failed, 2 warnings**.

The two full-suite failures are in the pre-existing
`tests/test_w06c0r1_contract.py` scope guard. Its fixed W06C0R1 base revision
rejects the later W-03B production/documentation paths as out-of-allowlist:
`verify_scope_diff()` reports a scope violation before any W-03B behavior is
asserted. No W06C0R1 evaluator/corpus file was changed in this package and the
failure is retained visibly for a separate scope-boundary decision.

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
- W06C0R1's repository-wide historical scope guard now blocks the full suite
  after unrelated later packages; that boundary is not changed here.

## OPEN FAILURES

- Two W06C0R1 scope-guard tests fail on the exact W-03B HEAD as described
  above. W-03B cannot be called fully accepted while the package-level full
  regression gate is unresolved.

## INDEPENDENT REVIEW

Contract: `SHIP` at `c3dcb10`.
Implementation review: **PENDING**.

## SCORE BEFORE / AFTER

- Scope/fail-closed safety: 7.5 → provisional 8.5 (focused evidence only;
  final score waits for independent review/full-gate resolution).
- Capture runtime: 7.5 → provisional 8.5 (focused evidence only;
  final score waits for independent review/full-gate resolution).

## VERDICT

`FIX-FIRST / REVIEW PENDING` — implementation is pushed, but independent
review and the unrelated W06C0R1 full-suite scope failure remain open.
