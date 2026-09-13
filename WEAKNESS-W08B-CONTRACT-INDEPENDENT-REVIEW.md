# W-08B Coordinated Backup Contract Independent Read-Only Review

**PACKAGE:** W-08B Coordinated Backup Snapshot Contract  
**CONTRACT REVISION:** `8057db7b28dc3cb35d6a1b4ca58fef4753e876a8`  
**REVIEW TYPE:** Independent read-only contract review  
**PHASE 20:** FROZEN / LOCKED  
**V2:** SHADOW  
**PRODUCTION/TEST CHANGES:** None

## Scope

I reviewed the contract against the current `scripts/memory_backup.py`,
`scripts/memory_store.py`, `scripts/state_store.py`,
`scripts/project_registry.py`, the shared file-lock implementation, runtime
install/migration lock order, and the existing backup/runtime tests. This is a
contract review only; no implementation or test files were changed.

## What the contract gets right

- The bounded read/validate/retry design is the correct boundary for the
  current architecture. It does not pretend that independent authorities can
  be made linearizable by taking locks that existing writers do not honor.
- The fixed four-source allowlist, explicit absent optional sources, raw-byte
  comparison, authority revision tokens, settings SHA-256, and aggregate
  descriptor digest are concrete enough to detect ordinary cross-read churn.
- The lock rule forbids holding one authority lock while acquiring another and
  keeps W-08B away from the existing memory→state migration lock order. The
  W-08C/W-08D, retrieval, V2 and Phase 20 boundaries are explicit.
- Manifest v3 is additive and the requirement to keep schema-1/schema-2
  verification and restore compatibility is correctly retained.
- The scope allowlist, registry/state identity checks, no raw source content in
  snapshot metadata, corruption visibility, bounded churn, and no-output-on-
  consistency-failure tests are the right safety surfaces.

## Findings requiring contract correction

### W08B-C1 — Retry bound and terminal error are not frozen (P1)

Section 4.2 says to use a finite constant “such as”
`MAX_SNAPSHOT_ATTEMPTS = 3`, and names `MemoryBackupConsistencyError` only as
an example. Sections 7 and 9 then require a typed bounded failure and a bounded
attempt/timeout budget. Two conforming implementations could therefore choose
different retry counts, exception classes, and evidence fields while both
claiming compliance. The acceptance test cannot be exact, and the latency
bound cannot be audited.

Before implementation, freeze all of the following in the contract:

- the exact constant value and whether it counts complete attempts or retries;
- the exact public exception class and its bounded fields, at minimum changed
  source names and attempt count;
- the mapping of lock timeout, optional-file disappearance, validation failure,
  and persistent churn to that class versus the existing
  `MemoryBackupError` subclasses;
- the maximum per-attempt lock/read wait and the resulting worst-case budget.

The exception text/evidence must remain content-free as already required.

### W08B-C2 — Archive publication is not no-clobber under concurrency (P1)

The current path is a preflight `output.exists()` check at
`scripts/memory_backup.py:369-371`, followed by
`temporary.replace(output)` at `:272`. A second creator can publish the same
destination after the check and be silently overwritten by the first creator.
This violates the contract's stated preservation of no-overwrite behavior and
is not covered by the listed archive-write fault test, which only covers a
failure after the destination decision.

The contract must require an atomic no-replace publication primitive (or an
explicit destination lock with a frozen ownership protocol), plus a two-creator
test proving exactly one succeeds and the other returns a bounded typed error
without changing the winner's bytes. The test must run on the supported Windows
and POSIX paths or document the platform-specific primitive and its fallback.

The contract should also state whether backup durability is required. The
current temp ZIP is closed before `replace` but is not explicitly fsynced, and
the parent directory is not synced. If W-08B claims durable archive publication,
require temp-file flush/fsync and parent-directory sync where supported; if it
claims atomicity only, say so explicitly and leave durability as a separate
package.

### W08B-C3 — Symlink containment needs a read-time race rule (P1)

Section 6.2 requires rejecting a source symlink that resolves outside
`.claude`, but does not say whether containment is checked for every read or
only once before the two-pass protocol. A symlink can be swapped after a
one-time `resolve()` check and before `read_bytes()`, allowing an outside file
to enter the archive while the ordinary byte comparison still succeeds.

Freeze one safe rule before implementation: either reject all source symlinks,
or open each source with a no-follow/descriptor-based containment check on every
pass, including optional sources. Add a deterministic symlink-swap or
no-follow test and require that the archive is absent on rejection. The vault
and `.claude` directory themselves need the same documented treatment.

## Non-blocking clarification

The double-read protocol proves a stable, mutually validated source set under
the contract's defined meaning of coherence; it does not provide an atomic
cross-authority transaction. The contract correctly avoids claiming that an
independent registry and memory writer share one linearization point. Keep this
definition in the implementation report so a stable-but-sequentially-written
set is not described as transactional.

Semantic validation errors currently include selected project identifiers in
some paths (for example the existing missing-registry message). The privacy
test should either include a sentinel project identifier or the implementation
should bound those errors to fixed labels. This is a clarification of the
already stated content-free evidence rule, not a request to redesign authority
validation.

## Gate review

| Gate | Result | Evidence |
|---|---|---|
| Bounded scope | PASS | Sections 1, 6 and 10 exclude authority rewrites, W-08C/D, V2 and Phase 20. |
| Stable read/validate/retry model | PASS WITH C1 | Two complete reads and descriptor comparison are specified; retry/error constants remain open. |
| Lock/deadlock boundary | PASS | No multi-authority lock is required; fixed source order and static lock inspection are required. |
| Manifest v3 / schema 1-2 compatibility | PASS | Additive v3 member and old archive verification/restore are explicit. |
| Revision/hash provenance | PASS | Memory, registry, state and settings token requirements are listed. |
| Corruption/scope/privacy | PASS WITH C3 | Fixed paths and metadata bounds are present; read-time symlink race needs an exact rule. |
| Archive atomicity/no-overwrite | FIX-FIRST | Existing check-then-replace race is not closed or tested. |
| Test/exit gates | FIX-FIRST | Tests are broad, but C1/C2/C3 need exact acceptance criteria. |
| W-08C/W-08D/Phase 20 boundaries | PASS | Explicitly deferred and non-authority scope preserved. |

## Required amendments before implementation authorization

1. Freeze the exact retry/error/timeout contract (W08B-C1).
2. Close and test concurrent no-clobber archive publication, and state the
   durability guarantee (W08B-C2).
3. Freeze a race-safe symlink/containment rule and test it (W08B-C3).
4. Add a privacy assertion for sensitive project identifiers or explicitly
   bound semantic validation errors.

## Verdict

**FIX-FIRST**

W-08B is not implementation-authorized at this contract revision. After the
four amendments above are recorded, a fresh independent review is required;
W-08C and W-08D remain blocked until W-08B is independently accepted.
