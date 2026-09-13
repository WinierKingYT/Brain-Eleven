# W-08B Coordinated Backup Snapshot Package Report

**PACKAGE:** W-08B  
**REVISION:** `47cb48b32425a458f542e24454b7e6e66d4146d1`  
**OBJECTIVE:** Make newly created backups prove a stable, mutually validated
source set across canonical memory, project registry, optional settings and
optional project state.

## Files changed

- `scripts/memory_backup.py`
- `tests/test_w08b_coordinated_backup.py`
- this package report

No canonical authority, writer protocol, restore policy, evaluation corpus or
Phase 20/V2 path was changed.

## Root causes addressed

- Sequential source reads could publish a cross-revision mixture.
- New manifests did not carry source revision/hash descriptors or an aggregate
  snapshot token.
- Archive publication used an unguarded replacement path and did not prove
  temporary-file and parent-directory durability.
- Source reads followed symbolic links/reparse points instead of failing closed.

## Implementation evidence

- New backups use manifest schema 3 and the fixed
  `stable-read-validate-retry-v1` protocol.
- Each attempt performs two complete reads in canonical, registry, settings,
  state order, validates both payload sets, compares raw bytes and descriptors,
  and retries at most three times within a five-second attempt budget.
- `MemoryBackupConsistencyError` exposes only bounded
  `changed_sources`, `attempts` and `reason` fields.
- Descriptors include presence, byte length, SHA-256 and authority-specific
  revision tokens; a canonical descriptor digest is verified before an archive
  is accepted.
- Schema 1 and schema 2 archive verification/restore remains supported.
- Source vault, `.claude` and source-file links/reparse points are rejected;
  POSIX reads use `O_NOFOLLOW` and Windows reads use a reparse-aware handle.
- Publication uses the requested archive sidecar lock with a five-second
  timeout, no-clobber check, temporary-file fsync and supported parent-directory
  fsync. Failed publication removes the newly created output and temporary file.

## Tests added

`tests/test_w08b_coordinated_backup.py` contains 17 focused tests covering:

- schema-3 descriptor and digest recomputation;
- explicit absent optional sources;
- canonical, registry, settings and state one-shot churn;
- optional source appearance/disappearance;
- persistent churn and exact bounded error fields;
- read-budget failure;
- stable corruption and privacy-safe error text;
- schema-2 compatibility;
- archive sync failure cleanup;
- vault, `.claude` and source symlink rejection.

## Tests executed

At exact revision `47cb48b`:

- `python -m pytest tests/test_w08b_coordinated_backup.py tests/test_memory_backup.py tests/test_pre13_runtime.py::test_backup_restore_preserves_runtime_receipts -q` — **26 passed**
- `python -m pytest tests -q` — **1009 passed, 2 warnings**
- `flake8 --select=E9,F63,F7,F82 scripts/memory_backup.py tests/test_w08b_coordinated_backup.py` — **passed**
- `python -m compileall -q scripts/memory_backup.py tests/test_w08b_coordinated_backup.py` — **passed**
- `git diff --check` — **passed**

The two full-suite warnings are pre-existing FastAPI/Starlette dependency
deprecation warnings. The baseline-v3 source fingerprint is unchanged because
`scripts/memory_backup.py` is outside the frozen fingerprint path set; no
evaluation corpus, holdout label, threshold or metric was changed.

## Safety metrics

- Stable mixed-revision publication: covered by mutation/retry tests.
- Persistent source churn: bounded at exactly three attempts; no archive output.
- Optional source presence transitions: explicit descriptor and retry behavior.
- Symlink/reparse source escape: fail-closed tests.
- Raw source/project identifier leakage in snapshot error evidence: covered.
- Existing no-overwrite and archive allowlist behavior: full backup suite passed.
- Canonical writes/revisions/CAS: no writer is called by W-08B.

## Quality metrics

**Before:** persistence consistency 7.0/10, with the W-08B mixed-source gap
open.  
**After:** package-local focused and full regression evidence passes; broader
score remains pending independent review.

## Known limitations

- `settings.json` remains included as exact raw backup payload when present, as
  required by the existing restore contract; redaction is a separate security
  package.
- W-08C state-reference TOCTOU and W-08D typed API lifecycle mutation remain
  deferred.
- The reader deliberately does not create a vault-wide or multi-authority lock.

## Open failures

None observed in the required local verification. Independent review is still
required for lock/deadlock proof, compatibility, path containment and privacy
claims.

**INDEPENDENT REVIEW:** REVIEW PENDING  
**SCORE BEFORE:** 7.0/10  
**SCORE AFTER:** pending independent review  
**VERDICT:** REVIEW PENDING

