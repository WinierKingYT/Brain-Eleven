# W-08B Coordinated Backup Snapshot Contract

**Status:** BOUNDED CONTRACT / PLAN ONLY  
**Revision audited:** `a38d1bba81d5d4cdee13a1678aa28ce2b4410eec`  
**Program:** Engineering Weak-Point Improvement Goal  
**Phase 20:** FROZEN / LOCKED  
**V2 runtime:** SHADOW  
**Implementation authorization:** Not granted by this document.

This contract closes the design boundary for W-08B, the coordinated backup
snapshot package. It does not authorize implementation. W-08B may change the
backup reader and manifest verifier only within the boundaries below. It must
not change a canonical authority, its write protocol, restore policy, or any
retrieval/intelligence behavior.

## 1. Objective and bounded scope

`scripts/memory_backup.py` currently reads up to four independent vault files
and then validates the combination:

1. `.claude/validated-memory.json` — canonical `MemoryStore`;
2. `.claude/project-registry.json` — canonical `ProjectRegistry`;
3. `.claude/settings.json` — optional runtime/client settings;
4. `.claude/project-state.json` — optional canonical `StateStore`.

The objective is to make a newly created backup prove that these exact bytes
were a stable, mutually validated source set. A backup must either contain a
coherent source set or fail visibly. It must never report success for a
cross-revision mixture that happened to pass the current structural checks.

In scope:

- `create_backup` source collection and its private read/validation helpers;
- bounded read/validate/retry evidence for the four fixed source paths;
- source revision/hash metadata in newly created manifests;
- verification of that metadata for the new manifest version;
- focused fault-injection tests and existing backup/regression evidence;
- preserving old archive verification and restore compatibility.

Out of scope for this package:

- changing `MemoryStore`, `StateStore`, `ProjectRegistry`, their locks,
  revisions, schemas, or write methods;
- changing `restore_backup`'s blank-vault/no-overwrite safety policy;
- W-08C state-reference TOCTOU protection;
- W-08D typed API lifecycle mutation;
- a new global persistence authority, a vault-wide writer lock, or a new
  snapshot database;
- Phase 20, V2 promotion, retrieval, capture, extraction, graph or context
  behavior.

## 2. Read-only reality audit

### 2.1 Current backup path

The current implementation demonstrates the exact gap that W-08B addresses:

- `scripts/memory_backup.py:207-224` reads the canonical bytes, then the
  registry, settings and state sequentially. It does not hold a coordinated
  boundary and does not re-read a source revision or hash before publishing.
- `scripts/memory_backup.py:160-204` validates the resulting combination,
  including memory scope/project identities against the registry and state
  project identities against the registry. This is a semantic validation, not
  a snapshot-consistency proof.
- `scripts/memory_backup.py:227-257` creates a manifest containing per-file
  SHA-256/byte counts, canonical revision/counts, state counts and migration
  metadata. It does not currently record registry revision, state store
  revision, settings hash as a source token, or one aggregate source snapshot
  token.
- `scripts/memory_backup.py:290-362` checks the existing file hashes and
  manifest counts while reading an archive, then re-runs `_validate_snapshot`.
  It has no new-source-set stability check because the archive is already
  immutable.
- `scripts/memory_backup.py:365-382` creates an archive and immediately
  verifies it, but its source payloads were collected before that verification.
  A successful archive therefore proves archive integrity and source validity,
  not that all source files belonged to one stable collection.

Existing archive safety that must remain intact includes the exact four archive
paths (`:47-56`), no overwrite (`:369-372`), manifest path allowlisting and
checksum checks (`:280-334`), and blank-vault/no-overwrite restore behavior
(`:407-447`).

### 2.2 Authority revisions and locks

The source authorities have independent boundaries:

| Source | Revision/token today | Writer boundary | Relevant evidence |
|---|---|---|---|
| MemoryStore | non-negative top-level `revision`; canonical schema normalization | `memory_store_lock(vault)` and reload/write inside `transact` | `scripts/memory_store.py:63-129`, `:131-177` |
| ProjectRegistry | W-08A additive non-negative `revision`; legacy missing value normalizes to `0` | `file_lock(self.path)`, latest load and CAS inside `_mutate` | `scripts/project_registry.py:106-149`, `:201-216` |
| StateStore | top-level `store_revision`, plus per-project revisions | `file_lock(self.path)`, latest load and revisioned transaction | `scripts/state_store.py:387-434`, `:598-657` |
| settings.json | no canonical revision; raw SHA-256 is the only stable token | runtime installer uses a per-settings lock in some paths; native clients may edit it independently | `brain_eleven/runtime/install.py:145-160`; `scripts/install-cross-project-memory.py:257-303` |

`MemoryStore.load`, `ProjectRegistry.load` and `StateStore.load` are read
operations without a lock held across the other authorities. The existing
multi-authority migration path acquires memory then state in one fixed local
order (`brain_eleven/runtime/migration.py:12-16`), while the native installer
holds its install lock and later acquires registry, state/migration and client
settings locks (`brain_eleven/runtime/install.py:103-160`). These are important
facts for the lock decision below.

### 2.3 Real callers and compatibility surface

The operational backup functions are imported by:

- `tests/test_memory_backup.py:14-23`, which exercises create, verify, restore
  and disaster-drill behavior;
- `tests/test_pre13_runtime.py:143-154`, which verifies runtime receipts and
  state/memory restoration;
- `conftest.py:53`, which exposes the legacy module for the test environment;
- the `scripts/memory_backup.py:508-538` direct CLI.

The package boundary and existing `scripts/memory_backup.py` authority are
therefore retained for W-08B. No caller may be forced to understand a new
snapshot token in order to create or restore a backup.

## 3. Decision: bounded read/validate/retry, not a multi-lock snapshot

W-08B freezes a **stable read/validate/retry protocol** as the snapshot
boundary. It must not acquire all authority locks at once.

The reason is deadlock and coverage risk. A new backup-wide lock would not be
honored by existing writers or native clients. Holding multiple existing locks
would also create a new ordering obligation across code that currently has
different scopes: an installer can hold its install lock while reaching a
registry/state/migration/settings path, and the migration helper already owns
memory before state. A backup that holds one authority while waiting for a
second could wait on a writer that is itself waiting for the first. This would
be a new cross-authority write contract, outside W-08B.

The frozen lock rule is therefore:

1. W-08B holds **no authority lock across two source reads**.
2. The implementation may use one source's existing lock for a single read,
   but it must acquire and release that lock before touching the next source.
3. If per-source locks are used, source order is fixed and documented as
   canonical, registry, settings, state. No nested lock is permitted.
4. The proof of consistency comes from a second complete read of all source
   bytes plus revision/hash validation, not from an undocumented lock order.
5. A lock timeout or source churn is a visible typed backup failure after the
   bounded attempt limit; it must not become an empty or partial archive.

This protocol remains safe when a writer does not use Brain-Eleven's lock,
including a native client changing settings: the raw bytes/hash stability
check still detects a change, and invalid transient bytes remain an explicit
validation error rather than being silently accepted.

## 4. Stable snapshot protocol

### 4.1 Fixed source set and order

Every new backup attempt examines exactly this ordered set:

```text
canonical/validated-memory.json -> .claude/validated-memory.json (required)
registry/project-registry.json -> .claude/project-registry.json (optional)
config/settings.json            -> .claude/settings.json (optional)
state/project-state.json        -> .claude/project-state.json (optional)
```

The archive path names are unchanged. Missing optional files are represented
by an explicit `present: false` token; they are not silently omitted from the
snapshot evidence. Missing canonical memory remains an immediate
`MemoryBackupError`, as today.

### 4.2 Per-attempt algorithm

The implementation must use the frozen constants
`MAX_SNAPSHOT_ATTEMPTS = 3` (three complete two-pass attempts, not three
retries) and `SNAPSHOT_ATTEMPT_BUDGET_SECONDS = 5.0`. It must not retry
forever. The reader takes no authority lock, so there is no authority-lock
wait inside an attempt; it checks a monotonic clock before and after each
source pass and fails with the typed consistency error when the five-second
budget is exceeded. One attempt is:

1. Read the four fixed source paths into raw byte payloads in the fixed order.
2. Validate the complete payload set using the existing semantic checks in
   `_validate_snapshot`.
3. Derive a source descriptor for every path (including absent optional
   paths), containing only presence, byte length, SHA-256, raw/normalized
   schema information and the appropriate source revision.
4. Read the same four source paths a second time in the same order.
5. Validate the second complete payload set.
6. Compare the first and second payload maps and all descriptors. If every
   byte and token is identical, the second payload map is the stable candidate.
   If any source differs, discard both maps and retry from step 1.
7. After the attempt limit, raise the public
   `MemoryBackupConsistencyError(MemoryBackupError)` with exactly these
   bounded fields: `changed_sources: Tuple[str, ...]`, `attempts: int` and
   `reason: str`. `attempts` is in `1..MAX_SNAPSHOT_ATTEMPTS` and `reason` is
   one of `source_churn`, `read_budget_exceeded` or
   `optional_source_changed`. The exception text contains only those fixed
   reason values, source archive-path names and the integer attempt count; it
   must not include raw memory, settings, state bytes, project roots or
   project identifiers.

The archive is not opened or published until step 6 succeeds. A source write
that completes between the first and second read is either detected and
retried, or, if it is complete before a later attempt, included consistently in
that later attempt. A write after step 6 cannot make the archived bytes mixed:
the archive contains the already captured stable payload map and its manifest
hashes prove exactly those bytes. A revision that changes and then returns to
the same serialized bytes is still detected for canonical authorities by its
monotonic revision; a settings rewrite that returns to identical bytes is
semantically the same payload.

A persistent malformed source is not hidden by retry. If a source cannot be
decoded or validated and there is no evidence that it changed during the
attempt, the existing `MemoryBackupError`/authority validation error is
surfaced. An implementation may retry a transient validation failure only when
the source token demonstrably changed, and must surface the typed consistency
error if churn continues.

The exact error mapping is frozen: a changed optional file (appearance,
disappearance or replacement) is a retry and then
`reason="optional_source_changed"`; a changed required source is a retry and
then `reason="source_churn"`; a stable malformed/corrupt/invalid-scope source
is the existing `MemoryBackupError` and is not converted into a retry success;
the five-second elapsed budget is `reason="read_budget_exceeded"`. W-08B
takes no authority lock, so authority lock timeout is not a source-read path;
the separate publication-lock timeout below is a `MemoryBackupError` with the
fixed label `archive publication lock timeout`.

### 4.3 Source descriptors and snapshot digest

The descriptor is a privacy-safe token, not a copy of source content:

| Source | Required descriptor fields |
|---|---|
| canonical | `present`, `sha256`, `bytes`, raw/normalized schema versions, `revision` |
| registry | `present`, `sha256`, `bytes`, raw/normalized schema versions, `revision`, whether revision was legacy-defaulted to `0` |
| settings | `present`, `sha256`, `bytes`, `revision: null` |
| state | `present`, `sha256`, `bytes`, schema version, `store_revision` |

The descriptor map is serialized with a specified canonical JSON encoding
(`sort_keys=True`, compact separators, UTF-8) and hashed into
`source_snapshot_sha256`. The digest input contains the four archive paths and
their descriptors in fixed order. It contains no source content, prompt,
secret, project root, or unbounded exception text. The `verified_at` timestamp
and attempt count are evidence metadata and are not used as the digest input.

The canonical and registry revision values are logical source revisions, not a
claim that revisions across authorities are comparable. The state value is
`store_revision`; the settings value is deliberately null because that file
has no canonical revision. A raw SHA-256 is mandatory for all present files.

## 5. Manifest version and archive compatibility

New archives use an additive manifest version **3**. The verifier must continue
to accept the currently supported schema-1 and schema-2 archives without
requiring fields that did not exist when they were created. Existing archives
are immutable; they are never rewritten in place to add W-08B metadata.

The supported set becomes `{1, 2, 3}`. For schema 1/2, current file inventory,
checksum, semantic validation, canonical metadata, migration metadata and
schema-2 state metadata remain the compatibility rules. No old archive is
called inconsistent merely because it lacks a W-08B snapshot token.

Schema 3 adds this manifest member while retaining the current `files`,
`canonical`, `state` and `migration` members:

```json
{
  "snapshot": {
    "protocol": "stable-read-validate-retry-v1",
    "attempts": 1,
    "verified_at": "<UTC timestamp>",
    "source_snapshot_sha256": "<64 hex chars>",
    "sources": {
      "canonical/validated-memory.json": {
        "present": true,
        "sha256": "<64 hex chars>",
        "bytes": 123,
        "raw_schema_version": 2,
        "normalized_schema_version": 2,
        "revision": 7
      },
      "registry/project-registry.json": {
        "present": true,
        "sha256": "<64 hex chars>",
        "bytes": 456,
        "raw_schema_version": 1,
        "normalized_schema_version": 1,
        "revision": 3,
        "revision_origin": "document"
      },
      "config/settings.json": {
        "present": true,
        "sha256": "<64 hex chars>",
        "bytes": 78,
        "revision": null
      },
      "state/project-state.json": {
        "present": false,
        "sha256": null,
        "bytes": 0,
        "store_revision": null
      }
    }
  }
}
```

The example is illustrative; the verifier must reject wrong types, unknown
source paths, duplicate descriptors, invalid hashes, negative/non-integer
revisions, inconsistent presence/byte values, a digest mismatch, or a
descriptor that does not match the archived payload and parsed source.

For a schema-3 archive, verification must prove all of the following before
returning `verified`:

- every present source descriptor matches the corresponding `files` entry;
- every absent source is absent from the archive and has an explicit absent
  descriptor;
- canonical/registry/state logical revisions match their archived payloads;
- the source descriptor digest recomputes exactly;
- existing scope, registry identity and state-reference validations still pass;
- no archive member exists outside the current exact allowlist.

The archive `archive_id` remains non-secret, random evidence metadata. Existing
CLI response fields remain compatible; new snapshot details may be exposed
only as bounded metadata and never as source content.

### 5.1 No-clobber publication and durability

The temporary ZIP must be closed, flushed and fsynced before publication. The
parent directory must be synced where the host supports directory fsync. The
final destination is protected by the existing `file_lock` sidecar for exactly
`ARCHIVE_PUBLICATION_LOCK_TIMEOUT_SECONDS = 5.0`; the lock covers the
destination-exists check and publication only and is never held while reading
an authority. Under that lock, an existing destination raises
`MemoryBackupError("Backup archive already exists")`; it is never replaced.
Two concurrent creators targeting one path must therefore produce exactly one
success and one bounded failure, with the winner's bytes unchanged. A lock
timeout raises the fixed `MemoryBackupError` label
`archive publication lock timeout`. The implementation must leave no
temporary file after a failed publication.

## 6. Invariants and safety boundaries

### 6.1 Coherence and authority

1. A newly created archive is either stable under the protocol or absent; no
   partial archive is reported as created.
2. A successful archive's `files` bytes, per-file hashes, source descriptors,
   logical revisions and aggregate snapshot digest all describe the same raw
   payload map.
3. `MemoryStore`, `ProjectRegistry` and `StateStore` remain the only canonical
   authorities. W-08B performs no canonical write and does not call a writer,
   bypass CAS, or change a revision.
4. Validation failures remain visible. Corruption is never treated as an empty
   source, missing optional registry/state, or successful backup.
5. The snapshot reader does not establish a second authority or an
   authority-wide lock. The only additional lock is the requested archive's
   publication sidecar described in Section 5.1. It may write only the
   requested archive's temporary/final file and its existing bounded evidence.

### 6.2 Scope and project isolation

1. Only the four fixed `.claude` source paths can enter the archive. No graph,
   context bootstrap, queue, evidence, cache, transcript or arbitrary path is
   added.
2. A project-scoped memory must still have a matching registry identity, and
   state project identities must still be registered, exactly as
   `_validate_snapshot` currently enforces at `:176-196`.
3. Global records must not gain project metadata, and project roots remain in
   the local registry only; no source descriptor or manifest may contain a
   filesystem root.
4. The source paths must resolve inside the selected vault's `.claude`
   directory. All vault, `.claude`, and source-path symlinks/reparse points
   are rejected on every read pass; the implementation must use a no-follow
   open/handle check (`O_NOFOLLOW` where available and the platform's reparse
   point/final-handle check on Windows). If the host cannot provide a no-follow
   check, the backup fails closed with a typed `MemoryBackupError` rather than
   falling back to ordinary `read_bytes`. A path identity/type change between
   pre-open and post-read is also a hard failure and cannot be turned into a
   successful retry. The vault argument may be resolved before this
   containment check, but no source path may escape the selected `.claude`.
5. Existing archive member traversal, backslash, duplicate-entry and unmanifested
   entry checks remain hard failures.

### 6.3 Privacy and settings

The existing backup contract includes the exact raw `settings.json` bytes when
that file is present. W-08B does not broaden that inclusion or redesign secret
redaction; such a policy change requires a separate security contract because
redaction would alter restore semantics. W-08B must nevertheless guarantee:

- snapshot metadata contains hashes, lengths and revisions only;
- result dictionaries, exception messages, retry evidence and logs never
  print raw settings, memory, state, prompt content or project identifiers;
- source path names are the fixed allowlist, not user-controlled archive paths;
- tests include sentinel settings, memory and project identifiers and assert
  they are absent from returned metadata/error text (the archive payload
  itself remains the explicitly documented backup data).

## 7. Fault-injection and concurrency evidence

The implementation is not accepted with only a happy-path manifest test. The
focused W-08B suite must deterministically inject each source mutation between
the first and second read, using normal authority writes where possible:

1. MemoryStore append or replace changes canonical revision between reads.
2. ProjectRegistry rename/status mutation changes registry revision.
3. StateService mutation changes `store_revision`.
4. Settings JSON is atomically rewritten and its hash changes.
5. An optional source appears or disappears between reads.
6. A source changes on every attempt; creation ends with the typed bounded
   consistency failure and no output archive.
7. A source is corrupt or contains invalid scope/identity; the error remains
   explicit and is not converted to a retry-success.
8. Archive write/replace failure leaves no success result and preserves the
   existing no-overwrite behavior.

For the one-shot mutation cases, the test must prove that the eventual archive
contains a single consistent revision/hash set, not merely that `create_backup`
returned. For the persistent churn case, inspect the output directory and
assert no final archive was published. The hooks must mutate only a temporary
test vault and must not change the real user vault.

The lock/deadlock evidence must include:

- static inspection proving no nested or multi-authority lock is acquired by
  the snapshot reader;
- a bounded concurrent-writer test showing that a writer completes and the
  backup either retries to a stable archive or returns the typed consistency
  error within the attempt/timeout budget;
- explicit lock-timeout/error mapping if the implementation elects to take a
  single per-source lock for a read;
- no reverse-order lock requirement added to `MemoryStore`, `StateStore`,
  `ProjectRegistry` or runtime install/migration paths.

The publication evidence must also exercise the exact five-second destination
lock budget with two concurrent creators and assert exactly one success, one
`MemoryBackupError`, unchanged winner bytes and no temporary files. A separate
fault test must prove temp-file fsync or parent-directory-sync failure cannot
report success. Symlink/reparse-point tests must cover the vault, `.claude`
directory and each optional source, including a swap between the two read
passes; every rejection must leave the final archive absent.

## 8. Test and regression plan

Existing assertions remain unchanged and must pass:

- `tests/test_memory_backup.py` (all current backup, restore, scope, tamper,
  idempotence and no-overwrite cases);
- `tests/test_pre13_runtime.py::test_backup_restore_preserves_runtime_receipts`;
- `tests/test_pre12_memory_state_caller_migration.py` compatibility checks;
- relevant `tests/test_pre12_project_caller_migration.py` and package-boundary
  checks for the legacy memory-backup module.

New focused tests should live in a bounded file such as
`tests/test_w08b_coordinated_backup.py` and cover:

- stable v3 manifest source descriptors and digest recomputation;
- registry revision, state `store_revision`, canonical revision and settings
  hash matching archived bytes;
- one mutation per source, optional-file appearance/disappearance, perpetual
  churn and corruption behavior;
- old schema-1/schema-2 archive verification and restore compatibility;
- symlink/reparse-point path containment (including read-time swap) and no
  raw-content/project-identifier metadata leakage;
- exact three-attempt/five-second bounded error fields and mapping;
- concurrent destination no-clobber publication and archive fsync/parent-sync
  failure behavior;
- no multi-lock/static adapter violation and bounded writer completion;
- output absence on failed consistency or archive publication.

Required verification commands at the exact implementation revision:

```text
.\.venv\Scripts\python.exe -m pytest tests/test_w08b_coordinated_backup.py tests/test_memory_backup.py tests/test_pre13_runtime.py -q
.\.venv\Scripts\python.exe -m pytest tests -q
flake8 --select=E9,F63,F7,F82 scripts/memory_backup.py tests/test_w08b_coordinated_backup.py
.\.venv\Scripts\python.exe -m compileall -q scripts/memory_backup.py tests/test_w08b_coordinated_backup.py
git diff --check
```

The full suite must remain green; existing warnings are reported rather than
hidden. No evaluation corpus, holdout label, retrieval threshold or baseline
metric may be changed by W-08B. If the source fingerprint changes only because
`scripts/memory_backup.py` changed, the official baseline protocol must record
that derived change separately; it is not permission to tune metrics.

## 9. Exit gate and review contract

W-08B stays `REVIEW PENDING` until every gate passes:

- exact-head focused tests prove stable source descriptors and all mutation/
  corruption/lock/path fault cases;
- old schema-1/schema-2 archives still verify and restore;
- full regression, critical flake8, compile/import sanity and diff check pass;
- no canonical authority, revision/CAS, lock order, scope or Phase 20/V2
  invariant changed;
- no raw source content appears in metadata, errors or evidence;
- an independent read-only reviewer checks the diff, contract, lock proof,
  manifest compatibility, fault evidence and caller scope;
- reviewer verdict is exactly `SHIP`, `FIX-FIRST` or `RETHINK`.

The implementer may not mark this package `SHIP`. Any failed consistency,
compatibility, security or deadlock gate leaves W-08B open and blocks W-08C.

## 10. Deferred work and package order

W-08B is the second W-08 package after the independently shipped W-08A
ProjectRegistry durability/CAS work. W-08C state-reference TOCTOU and W-08D
typed API lifecycle remain separate. W-08B must not use the snapshot protocol
as a reason to alter their write paths or to add a global lock that later
packages would inherit.

## 11. Package report template

```text
PACKAGE: W-08B
REVISION: <exact SHA>
OBJECTIVE: Coherent cross-authority backup snapshot
FILES CHANGED: <implementation/tests/docs>
ROOT CAUSES ADDRESSED: <mixed revisions, missing source tokens>
TESTS ADDED: <focused fault/concurrency/compatibility tests>
TESTS EXECUTED: <exact commands and results>
QUALITY METRICS BEFORE: <W-08 persistence score and evidence>
QUALITY METRICS AFTER: <package-local result; broader score remains pending review>
SAFETY METRICS: <mixed snapshot, corruption, path/scope, content leakage>
KNOWN LIMITATIONS: <settings raw backup policy and deferred W-08C/W-08D>
OPEN FAILURES: <none or exact failures>
INDEPENDENT REVIEW: REVIEW PENDING / SHIP / FIX-FIRST / RETHINK
SCORE BEFORE: <x/10>
SCORE AFTER: <x/10 or pending>
VERDICT: REVIEW PENDING
```

**Plan status: REVIEW PENDING — implementation başlamadı.**
