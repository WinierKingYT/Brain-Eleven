# W-08B Coordinated Backup Contract Independent Read-Only Review

**PACKAGE:** W-08B Coordinated Backup Snapshot Contract
**CONTRACT REVISION:** `17954cc9eae81d269249ce56c44b0d6112939288`
**SOURCE REVISION AUDITED BY THE CONTRACT:** `a38d1bba81d5d4cdee13a1678aa28ce2b4410eec`
**REVIEW TYPE:** Fresh independent read-only contract review
**PHASE 20:** FROZEN / LOCKED
**V2:** SHADOW
**PRODUCTION/TEST CHANGES:** None

## Scope and method

I independently reviewed the amended contract at exact revision
`17954cc`, the unchanged source surfaces named by the contract, the prior
FIX-FIRST review at `683130e`, and the amendment diff in `17954cc`. The source
revision named in the contract remains appropriate: no production or test
file changed between `a38d1bb` and `17954cc`; the later revisions amend the
contract and its evidence only. This review changes documentation only. It
does not authorize implementation and does not inspect an implementation as
if it already existed.

## Amendment verification

### Retry and terminal error boundary — PASS

Section 4.2 now freezes `MAX_SNAPSHOT_ATTEMPTS = 3` as three complete
two-pass attempts and `SNAPSHOT_ATTEMPT_BUDGET_SECONDS = 5.0` as the bounded
per-attempt budget. It names the public
`MemoryBackupConsistencyError(MemoryBackupError)`, its exact bounded fields
(`changed_sources`, `attempts`, `reason`), the allowed attempt range and
the three reason values. The mapping distinguishes required-source churn,
optional-source changes, stable validation/corruption errors and the read
budget. It also explicitly excludes authority-lock waits because the reader
holds no authority lock. This makes the acceptance tests and failure evidence
deterministic without allowing unbounded retries or content-bearing errors.

### Concurrent publication and durability — PASS

Section 5.1 closes the prior check-then-replace race with the existing
`file_lock` sidecar held for exactly five seconds around the destination
existence check and publication. It freezes the existing-destination error,
the lock-timeout label, exactly one winner for concurrent creators, unchanged
winner bytes and temporary-file cleanup. It separately requires temporary ZIP
flush/fsync and directory sync where supported. The lock is not held while
reading authorities, so this amendment does not introduce a cross-authority
lock order or a second persistence authority. The required two-creator and
fsync fault tests are explicit in Section 7/8.

### Read-time path and symlink safety — PASS

Section 6.2 now requires vault, `.claude`, and source symlink/reparse-point
rejection on every read pass, a no-follow open/handle check, platform-specific
reparse handling on Windows, and fail-closed behavior where the host cannot
provide that check. A path identity/type change between pre-open and
post-read is a hard failure, and the required read-time swap tests must leave
the final archive absent. This closes the prior resolve-once/read-later race
without expanding the fixed source allowlist.

### Privacy assertion — PASS

Section 6.3 now requires sentinel tests for settings, memory and project
identifiers and excludes raw content and project identifiers from metadata,
result dictionaries, exception messages, retry evidence and logs. The
contract keeps the explicitly documented raw `settings.json` archive payload
separate from bounded snapshot metadata and does not broaden that payload
policy.

## Remaining contract checks

- The fixed four-source allowlist, explicit absent optional descriptors,
  raw-byte comparison, logical revision/hash descriptors and aggregate digest
  define a stable read/validate/retry boundary without claiming a
  cross-authority transaction.
- Manifest version 3 is additive. Schema-1 and schema-2 verification and
  restore compatibility remain explicit, and old archives are not rewritten.
- Corruption and invalid scope/identity remain visible failures. The contract
  does not turn malformed data into an empty or successful backup.
- The contract keeps `MemoryStore`, `ProjectRegistry` and `StateStore` as the
  only canonical authorities, adds no writer/CAS bypass, and adds no
  authority-wide lock.
- W-08C state-reference TOCTOU and W-08D typed API lifecycle remain separate;
  no implementation may use W-08B to alter their write paths.
- Retrieval, capture, extraction, graph, context, V2 promotion and Phase 20
  remain outside the package.
- The contract explicitly states that a stable sequential read is not an
  atomic multi-authority transaction. This prevents an implementation report
  from overstating the guarantee.

## Gate review

| Gate | Result | Evidence |
|---|---|---|
| Exact contract revision | PASS | Amended contract is reviewed at `17954cc`. |
| Bounded scope | PASS | Sections 1, 6 and 10 exclude authority rewrites, W-08C/D, V2 and Phase 20. |
| Stable read/validate/retry | PASS | Sections 4.1–4.3 freeze source order, two-pass comparison, three attempts, five-second attempt budget and typed error mapping. |
| Lock/deadlock boundary | PASS | Sections 3, 5.1 and 6.1 prohibit nested/multi-authority locks and bound publication locking. |
| No-clobber publication/durability | PASS | Section 5.1 and Section 7 require destination locking, fsync evidence and temporary-file cleanup. |
| Path containment/race safety | PASS | Section 6.2 and Section 7 require no-follow/reparse checks on every pass and read-time swap tests. |
| Manifest v3 / schema 1–2 compatibility | PASS | Section 5 preserves additive v3 and legacy archive verification/restore. |
| Revision/hash provenance | PASS | Sections 4.2–5.1 bind descriptors, revisions, raw hashes and aggregate digest. |
| Corruption/scope/privacy | PASS | Sections 4.2, 6.2–6.3 and 7–8 keep failures visible and require sentinel privacy tests. |
| W-08C/W-08D/Phase 20 boundaries | PASS | Sections 1, 6 and 10 preserve the deferred boundaries. |
| Implementation authorization boundary | PASS | The document remains plan-only and requires a separate implementation report and independent code review. |

## Open findings

No contract-level P0/P1 finding remains at this revision. The implementation
must still prove every listed fault, platform and compatibility case; this
review does not treat a contract as evidence that the future implementation
has passed those gates.

## Verdict

**SHIP**

W-08B's bounded contract is accepted for implementation. This is a contract
verdict only: W-08B implementation remains `REVIEW PENDING` until its exact
head tests, security/path evidence, compatibility checks and independent
read-only implementation review pass. W-08C and W-08D remain blocked until
that package is independently shipped.
