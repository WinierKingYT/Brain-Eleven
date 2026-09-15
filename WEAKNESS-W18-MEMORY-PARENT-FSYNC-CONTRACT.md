# W-18 MemoryStore Parent-Directory Durability Contract

**Status:** BOUNDED CONTRACT / REVIEW PENDING  
**Revision audited:** `b8277e5ed59c77947446ba8041e9cfb45aa16e34`  
**Program:** Engineering Weak-Point Improvement Goal  
**Phase 20:** FROZEN / LOCKED  
**V2 runtime:** SHADOW  
**Implementation authorization:** This document defines the bounded package; implementation remains subject to the independent contract review.

## 1. Problem statement

`MemoryStore._write_unlocked()` flushes and fsyncs the temporary JSON file
before replacing `.claude/validated-memory.json`, but it does not sync the
containing directory after the rename. A crash after `replace()` can therefore
leave the new directory entry less durable than the file contents, even though
the transaction has returned successfully. The gap is an operational durability
issue; it does not change the canonical schema, revision/CAS behavior, backup
contract, or lock boundary.

## 2. Exact current evidence

At `scripts/memory_store.py:186-211`, `_write_unlocked()` currently:

1. normalizes the payload;
2. creates `.claude` if needed and copies an existing canonical file to the
   fixed backup path;
3. creates a temporary file beside the canonical file;
4. writes JSON, flushes the handle and calls `os.fsync(handle.fileno())`;
5. calls `temporary.replace(self.path)`;
6. removes a leftover temporary file in `finally`.

There is no `os.open(self.path.parent, ...)`/`os.fsync(directory_fd)` step after
the replacement. `transact()` at `:213-232` still owns the lock, reload,
expected-revision check and revision increment, while `replace()` and `append()`
at `:234-268` reuse that transaction boundary. `brain_eleven/memory/store.py`
is an identity-preserving adapter to this implementation and must remain so.

The repository already has the intended reference behavior in
`scripts/project_registry.py:74-84,87-103` and
`scripts/memory_backup.py:659-668`: directory fsync is attempted on POSIX and
explicitly skipped on Windows, where directory handles are not consistently
openable for fsync on supported versions. Those helpers are separate
implementations and are not imported or merged as a new persistence authority
by this package.

## 3. Bounded scope

In scope:

- `scripts/memory_store.py::_write_unlocked()` and a small private helper for
  syncing the canonical file's parent directory;
- focused durability/fault-injection tests and evidence;
- documentation and package report for W-18.

Out of scope:

- `MemoryStore` schema, normalization, backup representation, revision/CAS,
  lock implementation, record validation, or public method signatures;
- `brain_eleven/memory/store.py` adapter behavior;
- `StateStore`, `ProjectRegistry`, coordinated backup, runtime path safety,
  capture/retrieval, V2, Phase 20, and unrelated refactors.

## 4. Required invariants

1. The existing sidecar lock remains held by `transact()` while backup,
   temporary write, replacement and the directory-sync attempt run.
2. The temporary file is flushed and fsynced before replacement exactly as it is
   today. The existing fixed backup copy is created before replacement.
3. After a successful `temporary.replace(self.path)`, POSIX hosts sync
   `self.path.parent` through a directory descriptor and close that descriptor
   on every path. The helper must not follow a different path or sync the wrong
   directory.
4. Windows keeps the explicit supported-platform behavior: the helper returns
   without attempting an unsupported directory fsync. This limitation remains
   visible in the package report; it is not represented as a false POSIX pass.
5. An `OSError` from opening, syncing, or closing the parent directory is
   surfaced as `MemoryStoreError` from `_write_unlocked()`/the public transaction
   call. It must never be swallowed or reported as a successful durable write.
   The canonical file may already have been replaced when the post-publication
   sync fails; tests and reporting must describe this partial-publication state
   precisely rather than claim rollback.
6. A directory-sync failure must not leave the temporary file descriptor or
   temporary pathname behind. Existing JSON bytes, backup behavior, revision
   increments and lock/CAS conflict behavior stay unchanged.
7. No migration, caller, or adapter may write the canonical path directly; all
   writes continue through `MemoryStore.transact()`.

## 5. Required focused evidence

- On a POSIX-capable test host, monkeypatch/spy evidence proves the ordering:
  file-handle fsync → replace → parent-directory open/fsync → close.
- A parent-directory `os.open`/`os.fsync`/`os.close` fault is visible as a typed
  `MemoryStoreError`, with no success result and no leftover temporary file.
- A normal append/replace still increments revision once, creates the existing
  backup, preserves record identity and passes the current atomic-write tests.
- Stale `expected_revision` rejection happens before any write and remains
  byte/revision preserving.
- Two independent process writers still preserve both records and revisions.
- A Windows-path branch (real Windows CI or a controlled `os.name`/helper
  probe) proves that directory fsync is intentionally skipped while file
  fsync/replace behavior remains unchanged.
- Package and legacy `MemoryStore` object identity remains equal, and the
  `brain_eleven.memory` surface still reaches the same canonical implementation.

## 6. Test and verification plan

Focused existing tests, unchanged:

- `tests/test_memory_store.py` transaction, backup, stale revision, corrupt
  payload and multi-process writer tests;
- `tests/test_memory_validator.py` atomic write and canonical append tests;
- the existing W-15/W-16/W-17 runtime and append regression surfaces that
  exercise the shared MemoryStore boundary.

New tests should be isolated in a W-18 test module and must not alter production
behavior beyond the bounded directory-sync call. They must cover normal order,
fault visibility, cleanup, Windows skip semantics and identity.

Before acceptance, run the focused suite, the full `pytest tests -q` suite,
critical flake8 (`E9,F63,F7,F82`) on touched Python files, `compileall`, and
`git diff --check`. The package report must bind every result to the exact
implementation/test revision.

## 7. Exit gate

W-18 is eligible for an independent `SHIP` review only when all five gates
pass:

1. **Identity:** package/legacy `MemoryStore` surfaces remain the same object.
2. **Durability behavior:** parent-directory sync ordering and POSIX/Windows
   semantics are directly evidenced.
3. **Parity and safety:** existing backup, atomicity, revision/CAS, lock,
   corruption and concurrency behavior is unchanged; sync failures are visible.
4. **Full verification:** focused tests, full regression, critical flake8,
   compileall and diff-check pass.
5. **Independent review:** a separate read-only reviewer returns exactly
   `SHIP`, `FIX-FIRST`, or `RETHINK`; self-review is not acceptance.

Until the fifth gate returns `SHIP`, W-18 remains open and no score increase is
claimed. Phase 20 remains `FROZEN / LOCKED` and V2 remains `SHADOW`.

## 8. Estimate and rollback

Expected implementation size is approximately 15–35 production lines and
50–100 focused test lines. Rollback is a single revert of the W-18 code/test
commits; no canonical data migration or on-disk schema change is introduced.

**Plan status: REVIEW PENDING — implementation başlamadı.**
