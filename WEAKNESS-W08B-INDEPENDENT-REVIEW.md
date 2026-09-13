# W-08B Coordinated Backup Snapshot — Independent Implementation Review

**PACKAGE:** W-08B
**CONTRACT ACCEPTANCE:** `cce859f0cf4b9464e436c84b6984564b8350ad25`
**BASE IMPLEMENTATION:** `9627f4e8f3d6fe1b836d787b9dc3a0a416dc5cbb`
**PRIVACY CORRECTION:** `e4df824f20b87018e47c52aee8ecbc89f5b0e570`
**FOCUSED TEST COMMITS:** `47cb48b32425a458f542e24454b7e6e66d4146d1`, `98f4edd`, `f5766b5`, `e4df824`
**PACKAGE REPORT REVISION:** `e4df824f20b87018e47c52aee8ecbc89f5b0e570`
**EXACT HEAD REVIEWED:** `90336ee06dc3bf53bd6a1856be1c0ad72f8a6c98`
**REVIEW TYPE:** Fresh independent read-only implementation re-review
**PHASE 20:** FROZEN / LOCKED
**V2:** SHADOW

## Scope and method

The previous exact-head review at `673b39c` returned `FIX-FIRST` because
malformed registry validation could echo a project-like value in a backup
exception. The bounded correction at `e4df824` wraps that failure in a fixed,
content-free `MemoryBackupError` and adds a focused registry privacy test.

I independently reviewed the correction diff, package report, complete W-08B
implementation and current exact head, then reran the required local checks.
No production file, test file or pre-existing untracked evidence artifact was
modified by this review. Only this review and the engineering ledger are
documentation outputs.

## Verification evidence

| Gate | Result | Evidence |
|---|---|---|
| Exact revision binding | PASS | Correction `e4df824`; package report and final documentation head `90336ee`. |
| Focused W-08B and backup regression | PASS | `\.venv\\Scripts\\python.exe -m pytest tests/test_w08b_coordinated_backup.py tests/test_memory_backup.py tests/test_pre13_runtime.py::test_backup_restore_preserves_runtime_receipts -q` → **35 passed**. |
| Full regression | PASS | `\.venv\\Scripts\\python.exe -m pytest tests -q` → **1018 passed, 2 warnings**. Warnings are the pre-existing FastAPI/Starlette deprecations. |
| Critical static checks | PASS | Critical flake8, compileall and `git diff --check` all passed. |
| Stable two-pass source protocol | PASS | Fixed four-source order, complete second read, raw-byte/descriptor comparison, three-attempt bound and five-second attempt budget are implemented and fault-tested. |
| Schema 3 descriptors/digest | PASS | Descriptor fields, aggregate digest, optional-source presence and archived-byte matching are verified. Independent tamper probes rejected bad hash, negative revision, unknown source and presence mismatch. |
| Schema 1/2 compatibility | PASS | Existing schema-2 focused test passed; an independent temporary schema-1 archive conversion verified successfully. |
| Symlink/reparse containment | PASS | Vault, `.claude`, canonical source and all three optional source symlinks were independently rejected; between-pass vault, `.claude` and source swaps fail before publication. Windows reparse-aware code path is present. |
| Publication durability/no-clobber | PASS | Temporary fsync, parent sync, lock timeout, cleanup and two-creator no-clobber tests passed. |
| Canonical authority boundary | PASS | AST/static inspection found no authority lock in the reader; an independent temporary-vault probe monkeypatched MemoryStore, ProjectRegistry and StateStore writers to fail and `create_backup` completed without invoking them. Restore remains the pre-existing explicit write path. |
| Scope/deferred boundaries | PASS | The W-08B diff is limited to `scripts/memory_backup.py`, its bounded tests and evidence documents; no authority, retrieval, capture, V2 or Phase 20 behavior changed. |
| Privacy | PASS | The new registry sentinel test passes. A fresh malformed-registry probe now returns only `Project registry is invalid`, with no project identifier or root in the exception. Existing canonical/state privacy checks also pass. |

## Previously open finding — closed

`_validate_registry_payload()` now catches `ProjectRegistryError` and raises
the bounded message `Project registry is invalid` while preserving the
original exception as an internal cause. The added test places a project
identifier in both the registry identity and invalid status and asserts that
neither appears in the public exception. The independent probe reproduced the
same no-leak result after the correction.

This is a boundary redaction only. It does not change `ProjectRegistry`
validation, canonical authority, revision, lock or persistence behavior.

## Boundary review

- `MemoryStore`, `ProjectRegistry` and `StateStore` remain canonical
  authorities; W-08B does not add a writer, revision mutation or CAS bypass.
- The fixed archive allowlist, source descriptors, raw hashes and aggregate
  digest remain bounded and project-root-free.
- Schema 1/2 archives remain verifiable without schema-3 snapshot metadata.
- W-08C state-reference TOCTOU, W-08D typed lifecycle API, retrieval,
  capture, V2 promotion and Phase 20 remain deferred.
- No evidence indicates a P0/P1, cross-project archive selection, partial
  publication or unbounded retry.

## Verdict

**SHIP**

All W-08B contract gates pass at exact head `90336ee`. W-08B is independently
shipped; W-08C and W-08D remain separate bounded packages and must not be
implicitly folded into this result.
