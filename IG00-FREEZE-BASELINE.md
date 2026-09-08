# IG-00 — Freeze & Baseline

Status: **CLOSED / SHIPPED**. Authority: **CONTRACT** with explicitly labeled
evidence. Updated: 2026-09-08.

Implementation/evidence review HEAD:
`a6f9d3a04ae23e13e9d20b7b75f679a23076c467`.

Independent review: [IG-00-INDEPENDENT-REVIEW.md](IG-00-INDEPENDENT-REVIEW.md).
Verdict: **SHIP**. P0: **0**. P1: **0**.

## Bounded contract

Implement the program's feature freeze, exact baseline provenance, actual runtime
map and documentation authority. Preserve PRE-13 development and its failures;
do not reset master to PRE-12 or claim intelligence graduation. No extraction,
retrieval-quality tuning or IG-01 implementation belongs to this package.

Verified PRE-12 baseline:
`211bf2eb74cdb457b7b07430848bf6c6665e7f12`.
Preserved PRE-13 development checkpoint:
`7e6f55a82465f6fef7abf8318a451308bbe9a0e9`.
They serve different purposes. A green historical baseline does not validate
the development checkpoint or current changes.

Create immutable annotated tag `intelligence-graduation-baseline` only after
required matching CI results for the exact candidate SHA are verified. Record
workflow URLs and exact head SHA. If the tag already exists, verify its target;
never force-move or delete it. A mismatch or missing CI blocks baseline closure.

## Deliverables and acceptance

| Requirement | Current evidence boundary |
|---|---|
| Feature freeze | PROJECT-STATUS declares Phase 20 FROZEN and active program IG; graduation remains LOCKED. |
| Baseline commit | Exact SHA `211bf2eb74cdb457b7b07430848bf6c6665e7f12`: [Validation 34027088697](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34027088697) and [Docker 34027393699](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34027393699) both completed successfully. Authenticated run metadata binds both to this SHA. |
| Immutable baseline tag | Annotated `intelligence-graduation-baseline` created and pushed at the verified PRE-12 SHA; no master reset or force-move. |
| Runtime truth | RUNTIME-DATAFLOW distinguishes native and legacy installed/repository paths, gates and manual capture. Native V1 SessionStart compatibility and exact legacy-hook suspension passed focused tests; the real install now has one native Claude SessionStart entry and preserves unrelated `cbm` entries. |
| Documentation authority | DOCUMENTATION-AUTHORITY defines exact overrides and default path rules; stale scheduling claims are historical. |
| Validation / review | Exact-head local regression, isolated native smoke and independent read-only review pass. [Validation 34268326236](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34268326236) is green at the reviewed HEAD; [PRE-13 runtime 34268326222](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34268326222) retains its historical quality failure. |

Known baseline issue: native SHADOW at the preserved checkpoint measured V2
without emitting context; local repository legacy hooks exited when the native
marker existed. An independently installed global Claude V1 hook also exists.
IG-00 verified ownership in the installer and synthetic native boundary tests;
native client trust and real execution remain operational facts, not inferred
from configured commands or unit tests.

## Current implementation evidence

The correction uses the existing legacy V1 compiler only for the bounded
SessionStart bootstrap. It rechecks mode, project opt-in and canonical
revisions before returning context. UserPromptSubmit remains V2 SHADOW and
does not inject V2 context. The exact review revision
`762b5332f578c08d79fabf4d972b0371ae6de3a2` passed 680 non-integration tests,
42 integration/graduation tests and 179 requested focused tests. The local
coverage gate passed after four fail-closed router tests were added.

The current real installation was updated with the windowless installer on
2026-09-08. `doctor` reports both native clients configured, SHADOW mode and
service stopped when idle. The old global Claude Brain-Eleven SessionStart and
SessionEnd entries were removed from the active configuration and journaled for
uninstall restoration; unrelated `cbm-session-reminder` hooks remain. Native
client trust is still `VERIFY_IN_NATIVE_CLIENT` and has not been inferred.

On 2026-09-08, the open freeze review also closed a bounded semantic safety
issue. The legacy hash-seeded vector remains only as an explicitly unused test
helper; production `embed_text` returns no vector without a real provider,
`SemanticSearchEngine` abstains, and `HybridSearchEngine` switches to
lexical-only scoring. Embedding cache entries carry content hash, provider,
model and dimension metadata and are rejected on mismatch. The focused semantic
and API suite passed 61 tests; the full non-integration suite passed 665 tests.
This evidence strengthens IG-00 reliability. It does not constitute IG-01
evaluation or Brain-Eleven intelligence graduation.

On 2026-09-08, exact-head local verification at
`762b5332f578c08d79fabf4d972b0371ae6de3a2` also passed critical flake8,
Bandit, `git diff --check`, `pyproject.toml` parsing and import/compile
sanity. The isolated native smoke used temporary Claude and Codex
configuration/vaults only: Claude emitted successful `SessionStart` and
`UserPromptSubmit` hook responses, Codex emitted a successful
`UserPromptSubmit` hook, and separate Claude/Codex Golden E2E runs produced
queue terminal states `COMMITTED`/`PROCESSED` with verified canonical effects.
No live user configuration was changed. Client model calls were unavailable
without credentials, so this is hook/runtime evidence rather than a successful
model turn or installed-client trust decision.

The review branch triggers exact-head remote workflows. [Validation
34268326236](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34268326236)
completed successfully at the reviewed SHA, including cross-platform tests,
coverage, privacy, security, dependency and Docker jobs. Public/evidence jobs
conditioned on `master` were skipped and remain explicitly not applicable on
the review branch. [PRE-13 runtime
34268326222](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34268326222)
passed both runtime OS jobs and security checks; its overall failure is the
visible historical PRE-13 holdout quality failure (runtime precision 0.1368,
required recall 0.2941, zero leakage).

The preferred master-targeted draft PR could not be created because the GitHub
connector returned HTTP 403 (`Resource not accessible by integration`); exact
push-triggered CI remains revision-bound. Independent acceptance is recorded in
`IG-00-INDEPENDENT-REVIEW.md`.

## Review and next-package boundary

Acceptance requires exact baseline SHA, matching green CI, immutable tag,
feature freeze, authoritative status, runtime paths, stale-document registry and
independent review. These gates are now closed for IG-00. Windows helpers must
remain hidden; do not launch visible Python consoles or browser panels during
verification.

Only after SHIP can IG-01 open. Its first work is a bounded evaluation contract,
including answerability, corpus provenance, private data handling and accepted
V1-equivalent recall. Existing synthetic failures remain historical evidence;
they neither block declaring a feature freeze nor prove product quality.
