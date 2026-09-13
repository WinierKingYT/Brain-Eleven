# W-08B Coordinated Backup Snapshot — Independent Implementation Review

**PACKAGE:** W-08B  
**CONTRACT ACCEPTANCE:** `cce859f0cf4b9464e436c84b6984564b8350ad25`  
**IMPLEMENTATION:** `9627f4e8f3d6fe1b836d787b9dc3a0a416dc5cbb`  
**FOCUSED TEST COMMITS:** `47cb48b32425a458f542e24454b7e6e66d4146d1`, `98f4edd`, `f5766b5`  
**PACKAGE EVIDENCE REVISION:** `60652326459d64103083a1f4c8af505c617f0b11`  
**EXACT HEAD REVIEWED:** `673b39cf46ed1c001202b37e1f1db8fb110fba01`  
**REVIEW TYPE:** Independent read-only implementation review  
**PHASE 20:** FROZEN / LOCKED  
**V2:** SHADOW

## Scope and method

I reviewed the accepted W-08B contract, the implementation diff from the
contract source revision, the bounded focused tests, the package report and
the current exact head. I reran the required local checks independently. No
production file, test file or pre-existing untracked evidence artifact was
modified by this review. Only this review and the engineering ledger are
documentation outputs.

## Verification evidence

| Gate | Result | Evidence |
|---|---|---|
| Exact revision binding | PASS | Implementation `9627f4e`; package evidence `6065232`; final docs head `673b39c`. |
| Focused W-08B and backup regression | PASS | `\.venv\\Scripts\\python.exe -m pytest tests/test_w08b_coordinated_backup.py tests/test_memory_backup.py tests/test_pre13_runtime.py::test_backup_restore_preserves_runtime_receipts -q` → **34 passed**. |
| Full regression | PASS | `\.venv\\Scripts\\python.exe -m pytest tests -q` → **1017 passed, 2 warnings**. Warnings are the pre-existing FastAPI/Starlette deprecations. |
| Critical static checks | PASS | Critical flake8, compileall and `git diff --check` all passed. |
| Stable two-pass source protocol | PASS | Fixed four-source order, complete second read, raw-byte/descriptor comparison, three-attempt bound and five-second attempt budget are implemented and fault-tested. |
| Schema 3 descriptors/digest | PASS | Descriptor fields, aggregate digest, optional-source presence and archived-byte matching are verified. Independent tamper probes rejected bad hash, negative revision, unknown source and presence mismatch. |
| Schema 1/2 compatibility | PASS | Existing schema-2 focused test passed; an independent temporary schema-1 archive conversion verified successfully. |
| Symlink/reparse containment | PASS | Vault, `.claude`, canonical source and all three optional source symlinks were independently rejected; between-pass vault, `.claude` and source swaps fail before publication. Windows reparse-aware code path is present. |
| Publication durability/no-clobber | PASS | Temporary fsync, parent sync, lock timeout, cleanup and two-creator no-clobber tests passed. |
| Canonical authority boundary | PASS | AST/static inspection found no authority lock in the reader; an independent temporary-vault probe monkeypatched MemoryStore, ProjectRegistry and StateStore writers to fail and `create_backup` completed without invoking them. Restore remains the pre-existing explicit write path. |
| Scope/deferred boundaries | PASS | Only `scripts/memory_backup.py` and its bounded test file changed; no authority, retrieval, capture, V2 or Phase 20 files changed. |
| Privacy | **FAIL** | Registry validation can echo attacker-controlled project-like text in an exception; see the open finding below. |

## Open finding

### W08B-P1 — malformed registry validation leaks project identifiers

`_validate_registry_payload()` in `scripts/memory_backup.py` directly calls
`ProjectRegistry._validate()` (around lines 345–349). The validator formats an
untrusted status value in `ProjectRegistryError` at
`scripts/project_registry.py:164`:

```text
Unsupported project status: {status}
```

An independent temporary-vault probe placed the sentinel
`project-secret-identifier` in the malformed registry status. `create_backup`
raised `ProjectRegistryError` whose text contained that sentinel. The probe
did not touch the user vault or repository data.

This violates W-08B contract §6.3, which requires project identifiers and raw
source values to stay out of result metadata, exception messages, retry
evidence and logs. The package report currently claims privacy-safe error
evidence, so that claim is not yet evidence-backed for malformed registry
input.

Required bounded correction: convert registry validation failures at the
backup boundary into a fixed, content-free backup error and add a focused
registry privacy sentinel test. Re-run the W-08B focused suite and full
regression after the correction. No registry validator redesign or authority
change is required.

## Boundary review

- `MemoryStore`, `ProjectRegistry` and `StateStore` remain canonical
  authorities; W-08B does not add a writer, revision mutation or CAS bypass.
- The fixed archive allowlist, source descriptors, raw hashes and aggregate
  digest remain bounded and project-root-free.
- Schema 1/2 archives remain verifiable without schema-3 snapshot metadata.
- W-08C state-reference TOCTOU, W-08D typed lifecycle API, retrieval,
  capture, V2 promotion and Phase 20 remain deferred.
- No evidence indicates a P0, a cross-project archive selection, a partial
  publication or an unbounded retry.

## Verdict

**FIX-FIRST**

The implementation passes the functional, durability, compatibility,
concurrency, path and authority gates, but the explicit contract privacy gate
is not satisfied. W-08B remains open and W-08C/W-08D stay blocked until the
bounded registry error redaction and its focused evidence are independently
rechecked.

