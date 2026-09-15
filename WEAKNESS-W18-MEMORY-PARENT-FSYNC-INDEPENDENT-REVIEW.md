# W-18 MemoryStore Parent-Directory Durability — Independent Review

**Implementation revision:** `bc393e746cd230631d7abc6a9b586599e3f3831a`

**Test revision:** `214277a3448f673ef6b1ab3d39c01e6e14d0b548`

**Final package-report revision:** `287c438353d32b59bbb7e0490845c083bde4899d`

**Reviewer:** `/root/w10_exact_review` (read-only, independent context)

**Verdict:** **SHIP**

## Scope reviewed

The reviewer checked the W-18 contract, the exact MemoryStore write-path diff,
focused tests, full regression and static gates. Review was limited to the
post-replace parent-directory durability gap; canonical schema, backup format,
lock/CAS semantics, package identity, StateStore, ProjectRegistry, runtime
path safety, V2 and Phase 20 were not expanded.

## Evidence

- POSIX ordering proves temporary-file fsync occurs before replace, followed by
  parent-directory open/fsync/close.
- Explicit `os.open`, `os.fsync` and `os.close` fault cases surface typed
  `MemoryStoreError` and leave no temporary file behind.
- Partial publication after a post-replace sync failure is reported precisely;
  no false rollback claim is made.
- Windows directory-sync skip behavior is explicit and tested; existing file
  fsync/replace behavior remains intact.
- Existing backup, stale revision/CAS, lock, schema, corruption and identity
  tests remain green.
- Focused canonical suite: **29 passed, 4 skipped**.
- Full suite: **1266 passed, 4 skipped, 2 warnings**.
- Critical flake8, compileall and diff-check passed.

## Findings

No P0, P1 or P2 issue remains within the W-18 contract. The existing backup
`copy2` durability limitation and Windows directory-fsync limitation are
explicitly bounded in the package report and are outside this package.

**SHIP** — W-18 parent-directory durability is independently accepted.
