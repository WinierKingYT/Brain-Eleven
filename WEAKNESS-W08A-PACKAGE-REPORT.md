# W-08A Package Report — Project Registry Durability and CAS

## PACKAGE

W-08A — ProjectRegistry durability and stale-writer detection

## REVISION

`20407ee` (implementation `7fc2860`, focused tests `a2b065d`, official
source-fingerprint evidence `20407ee`)

## OBJECTIVE

Harden the existing project-registry authority with additive revision metadata,
optional stale-writer detection, durable atomic writes, a fixed validated backup
envelope and stale-safe rollback. No new authority or caller migration was
introduced.

## FILES CHANGED

- `scripts/project_registry.py`
- `brain_eleven/projects/registry.py`
- `brain_eleven/projects/__init__.py`
- `tests/test_w08a_project_registry.py`
- `evals/reports/baseline-v3.json` (source fingerprint only; corpus, metrics and
  invariants unchanged)

## ROOT CAUSES ADDRESSED

- Registry writes had no revision/CAS boundary.
- Registry temporary files were not flushed/fsynced before replacement.
- The registry had no fixed backup envelope or stale-safe rollback surface.
- New registry error/backup symbols were not exposed through the package surface.

## TESTS ADDED

Eight focused W-08A tests cover legacy schema normalization and upgrade,
stale conflict plus explicit retry, compatibility callers, backup envelope,
monotonic/idempotent rollback, stale rollback, missing/corrupt backup,
fsync/main persistence failures, parent-directory sync invocation and package
identity. The final focused file contains ten tests after the two durability
fault cases were added.

## TESTS EXECUTED

- W-08A focused tests: **10 passed**.
- Registry/scope/package-boundary/caller/backup/capture/remember suite: **70
  passed**.
- Baseline snapshot guard: **5 passed**.
- Full `pytest tests -q`: **992 passed, 2 dependency deprecation warnings**.
- Critical flake8 (`E9,F63,F7,F82`) on changed Python files: **passed**.
- `compileall` on changed Python files: **passed**.
- `git diff --check`: **passed**.

## QUALITY METRICS BEFORE/AFTER

Persistence/consistency baseline: **7.0/10**. W-08A addresses only the
registry sub-surface; the broader W-08 score is not graduated by this package.
No retrieval, intelligence, V2 or Phase 20 metric was changed.

## SAFETY METRICS

- Silent stale registry overwrite under explicit CAS: **0** in focused tests.
- Lost update after explicit loser retry: **0**.
- Corrupt/missing backup treated as empty: **0**; typed error is raised.
- Registry rollback revision regression: **0**; revisions remain monotonic.
- New memory/state/graph/capture authority writes: **0**.
- Scope/project identity leakage: **0** in existing and focused tests.

## KNOWN LIMITATIONS

Callers that omit `expected_revision` retain the existing latest-snapshot
mutation behavior for compatibility. Coordinated multi-authority backup
snapshots, StateStore-to-MemoryStore reference TOCTOU and typed API lifecycle
updates remain deferred W-08B/W-08C/W-08D packages.

## OPEN FAILURES

- Independent read-only package review is pending.
- Two pre-existing FastAPI/Starlette dependency deprecation warnings remain.

## INDEPENDENT REVIEW

REVIEW PENDING — the implementer has not self-accepted this package.

## SCORE BEFORE/AFTER

Persistence and concurrency: **7.0 → pending independent review**. No other
score is changed by W-08A.

## VERDICT

REVIEW PENDING
