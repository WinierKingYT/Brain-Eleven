# W-01 Package Report — V1 Context Related-Note Boundary

**PACKAGE:** W-01 / V1 context related-note boundary  
**REVISION:** `1a586d3`  
**OBJECTIVE:** Prevent V1 context compilation from reading a related note
outside the configured `Kararlar` directory.  
**FILES CHANGED:** `scripts/context-compiler.py`,
`tests/test_context_compiler.py`, `evals/reports/baseline-v3.json`  
**ROOT CAUSES ADDRESSED:** Untrusted `related_notes` values were concatenated
with a filesystem directory without portable path validation or post-resolve
containment.  

## Implementation

`ContextCompiler._resolve_related_note()` now rejects null/empty values,
POSIX and Windows separators, traversal, absolute/drive/UNC paths and values
that resolve outside the configured notes directory. Symlink escapes are
blocked by resolving both root and candidate before the containment check.
Unreadable or malformed optional notes remain bounded misses. Valid notes keep
the existing first-200-character projection and wikilink fallback.

No ranking, V2, canonical memory, hook or Phase 20 behavior was changed.

## Tests executed

- Focused context/scope/router suite: **88 passed**.
- Full suite after the official baseline refresh: **951 passed, 2 warnings**.
- Critical flake8 (`E9,F63,F7,F82`): **PASS**.
- `compileall`: **PASS**.
- `git diff --check`: **PASS**.
- Baseline verification: `baseline-v3 --check` **PASS**.

The baseline report refresh was performed with the official writer, not by
hand. Its only diff is the revision-bound `source_fingerprint`; metrics remain
the deterministic 130-case values (`context_precision=0.18`,
`context_recall=0.8038461538461539`).

## Safety metrics

- Traversal/absolute/mixed-separator reads: **0**.
- Symlink escape reads: **0**.
- Valid in-bound note regressions: **0**.
- Canonical write paths added: **0**.
- New P0/P1 findings: **0**.

## Known limitations

V1 still injects continuity markdown without a complete content policy, and
V1 ranking remains task-unaware. Those are separate W-06/W-07 packages; this
package intentionally does not tune retrieval or promote V2.

## Independent review

An independent read-only review re-ran the diff and evidence and returned
**SHIP**. The reviewer specifically verified path classes, symlink containment,
valid-note parity, focused tests, full suite and baseline consistency.

## Quality and verdict

**QUALITY METRICS BEFORE:** Related-note filesystem boundary was unverified;
full suite was 943 passed before this package.  
**QUALITY METRICS AFTER:** Boundary tests pass; full suite is 951 passed.  
**SCORE BEFORE/AFTER:** Context compilation safety 5.0 → 6.0 (provisional;
task-aware ranking and V2 remain open).  
**OPEN FAILURES:** None for W-01. W-02–W-08 remain open as separate bounded
findings in `ENGINEERING-WEAK-POINTS-AUDIT.md`.  
**VERDICT:** SHIP
