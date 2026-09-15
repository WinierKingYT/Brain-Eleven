# W-18 MemoryStore Parent-Directory Durability Package Report

**PACKAGE:** W-18

**IMPLEMENTATION REVISION:** `bc393e746cd230631d7abc6a9b586599e3f3831a`

**TEST REVISION:** `214277a3448f673ef6b1ab3d39c01e6e14d0b548`

**STATUS:** CLOSED / SHIP

## OBJECTIVE

Persist the canonical MemoryStore directory entry after atomic replacement on
hosts that support directory fsync, while preserving the existing backup,
revision/CAS, lock, schema and temporary-file behavior.

## FILES CHANGED

- `scripts/memory_store.py` — private parent-directory fsync helper and the
  post-replace call inside `_write_unlocked()`;
- `tests/test_w18_memory_parent_fsync.py` — ordering, failure visibility,
  cleanup, Windows skip and identity evidence;
- `WEAKNESS-W18-MEMORY-PARENT-FSYNC-CONTRACT.md` — bounded contract.

No canonical schema, public MemoryStore method, lock/CAS boundary, backup
format, package adapter, StateStore, ProjectRegistry, runtime path, V2 or Phase
20 behavior was changed.

## ROOT CAUSE ADDRESSED

`_write_unlocked()` previously fsynced only the temporary file before
`temporary.replace(self.path)`. It did not fsync the containing directory, so a
power loss after the rename could lose the directory entry even though the
file contents had been flushed.

## IMPLEMENTATION

`_fsync_parent_directory(path)` returns explicitly on Windows because directory
handles are not consistently openable for fsync there. On POSIX it opens
`path.parent`, calls `os.fsync()` and closes the descriptor in `finally`.
`_write_unlocked()` invokes it immediately after the existing atomic replace.
Any `OSError` remains visible through the existing `MemoryStoreError` wrapper;
the report does not claim rollback after a post-replace sync failure.

## TESTS ADDED

- package/legacy MemoryStore identity;
- POSIX ordering: file fsync, replace, parent open/fsync/close;
- POSIX parent-sync failure visibility and temporary-file cleanup;
- explicit Windows directory-fsync skip behavior.

## TESTS EXECUTED

- W18 plus existing canonical MemoryStore/validator tests: **29 passed, 4
  skipped** on Windows (the POSIX-only ordering and three fault cases are
  skipped by platform).
- Full Windows suite at implementation revision `bc393e7`: **1266 passed, 4
  skipped, 2 warnings**.
- WSL Ubuntu direct parent-sync order smoke: **PASS**.
- WSL Ubuntu direct parent-sync fault visibility/cleanup smoke: **PASS**.
- Critical flake8 (`E9,F63,F7,F82`) on touched Python files: **PASS**.
- `compileall` on touched Python files: **PASS**.
- `git diff --check`: **PASS**.

## QUALITY METRICS BEFORE / AFTER

Before: file contents were fsynced but the post-replace directory entry was not.

After: supported POSIX hosts sync the parent directory after replacement;
Windows keeps the documented file-fsync-only behavior. Revision, backup,
atomic replace and stale-writer behavior remain unchanged.

## SAFETY METRICS

- Canonical authority count: unchanged.
- Lock/CAS boundary: unchanged.
- Schema and record identity: unchanged.
- Sync/open/close errors: surfaced as `MemoryStoreError`.
- Temporary-file cleanup after sync failure: verified.
- No prompt, memory, token or secret content enters evidence.

## KNOWN LIMITATIONS

- Backup `shutil.copy2()` durability is unchanged and remains outside W-18.
- Windows directory-entry fsync is explicitly unsupported by this helper; file
  handle flush/fsync and atomic replace remain unchanged.
- A post-replace directory fsync failure can leave the new canonical bytes
  published with durability uncertain; the failure is visible, but there is no
  implicit rollback.

## OPEN FAILURES

No focused or full-suite failure remains. Independent read-only implementation
review returned **SHIP**. W-07B remains `FIX-FIRST / NOT ACCEPTED`, W-12A
remains open, and Phase 20 remains `FROZEN / LOCKED` with V2 `SHADOW`.

## INDEPENDENT REVIEW

A separate read-only reviewer `/root/w10_exact_review` inspected the exact code
revision `bc393e746cd230631d7abc6a9b586599e3f3831a`, test revision
`214277a3448f673ef6b1ab3d39c01e6e14d0b548` and package report revision
`287c438353d32b59bbb7e0490845c083bde4899d`. The reviewer verified POSIX and
Windows semantics, all three parent-sync fault paths, ordering, cleanup,
partial publication, backup, lock/CAS, schema and identity parity.

**SHIP** — independent review is recorded in
`WEAKNESS-W18-MEMORY-PARENT-FSYNC-INDEPENDENT-REVIEW.md`.

## SCORE BEFORE / AFTER

Persistence/concurrency: **8.0 → 8.5**

Operational durability: **parent-entry sync missing → bounded supported-host
parent-entry sync with visible failure**

## VERDICT

**SHIP** — implementation, tests and independent evidence are pushed at their
exact revisions.
