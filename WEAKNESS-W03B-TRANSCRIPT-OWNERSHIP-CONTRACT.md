# W-03B — Transcript Ownership and Session Provenance Contract

**Status:** CONTRACT REVIEW PENDING — implementation is not authorized
**Package:** W-03B
**Parent:** W-03A path confinement / W-04 late locator durability
**Phase 20:** FROZEN / LOCKED
**V2:** SHADOW

## Problem

W-03A confines a transcript locator to a trusted Claude/Codex root, but that
proves only filesystem location. A read-only native smoke reproduced a P1
failure: a file inside the trusted Claude root, belonging to an unrelated
session, was read while the hook-supplied `session_id` and project identity
were attached to the evidence. `capture_provenance.py` deliberately leaves
session/project ownership to a later package; `worker.py` and `evidence.py`
currently accept the claimed values without an ownership match.

The package must make an ownership decision before transcript lines become
Evidence or candidates. It may safely abstain; it may not infer ownership
from raw transcript content or silently relabel a foreign session.

## In scope

- A deterministic, content-free ownership check at the worker/evidence
  boundary, after W-03A path confinement and before `read_increment` results
  are persisted.
- A versioned adapter for the currently supported Claude and Codex native
  transcript locator/metadata shapes, with explicit `UNKNOWN` handling when a
  client format cannot provide a trustworthy session or project binding.
- Session and project binding to the already validated queue event:
  `client`, `session_id`, `project_id`, and resolved `project_root`.
- Fail-closed result mapping: an ownership mismatch or unavailable binding
  must remain visible as a bounded processing/dead-letter code and must not
  create Evidence, review candidates, canonical effects, or receipts that
  claim successful capture.
- Privacy-safe evidence: mismatch diagnostics may contain only codes,
  client, hashed session/path identities, and bounded counts. Raw transcript
  content and full paths are excluded.
- A stable file-identity check spanning validation and read. The reader must
  use one opened handle (or an equivalent pre/post identity token) and reject
  replacement/TOCTOU changes; path re-resolution alone is insufficient.
- Retry semantics for a temporarily unavailable transcript or metadata must
  remain compatible with W-04: a trusted, not-yet-available locator remains
  retryable, while an ownership mismatch is not endlessly retried.

## Native binding rules

The implementation must freeze these current-format adapters with fixtures
that contain metadata keys only (fixture output must never print transcript
content). The queue event currently stores a privacy-preserving normalized
session key, not the raw client identifier: `client + ':' +
sha256(raw_session_id)` (see `worker.enqueue`). Adapters compare a raw native
identifier by applying that exact normalization; they never reverse the hash
and never add raw session IDs to durable diagnostics.

- **Claude:** resolve the event project root to an absolute normalized string,
  replace each Windows `:` and path separator (`\\` or `/`) with `-` without
  case folding, and compare the resulting slug exactly to the transcript's
  parent directory name (for example, `C:\\Users\\faruk\\Documents\\Brain-Eleven`
  maps to `C--Users-faruk-Documents-Brain-Eleven`). The filename stem must
  hash-normalize to the event session key, and at least one native record must
  contain `sessionId` whose hash-normalized value equals that key. All three checks are
  required; a missing or conflicting field is `TRANSCRIPT_OWNERSHIP_UNVERIFIED`
  or `TRANSCRIPT_OWNERSHIP_MISMATCH`.
- **Codex:** a native `session_meta`/metadata record must contain
  `payload.session_id` whose hash-normalized value equals the event session
  key and a `payload.cwd` resolving exactly to the event's registered
  `project_root`. The dated filename is not an identity proof by itself.
  Missing or conflicting fields fail closed with the same bounded codes.

Read-only native-format evidence collected on 2026-09-13 confirms these
metadata keys without retaining content: Claude records expose top-level
`sessionId`; Codex records expose a top-level `payload` containing
`session_id` and `cwd`. If a future client format lacks this evidence, its
adapter remains explicitly unsupported and rejects capture until a new
contract revision is reviewed.

The Claude slug is not assumed injective. If two registered project roots
produce the same slug, ownership is `UNVERIFIED` and capture is rejected;
the implementation must include a collision fixture.

These rules are intentionally stricter than the current synthetic fixtures.
End-to-end fixtures that currently omit ownership metadata must be enriched
with the minimal metadata above; direct parser tests may continue to exercise
message-only documents. No production compatibility exception or test-only
trust bypass is allowed.

## Out of scope

- Changing canonical MemoryStore, StateStore, ProjectRegistry, lifecycle, or
  authority behavior.
- Automatic project discovery, slug guessing, path-to-project inference, or
  treating transcript text as identity evidence.
- Changing extraction, retrieval, ranking, context compilation, V2 rollout,
  reminder/maintenance delivery, or Phase 20.
- Reworking W-03A root confinement or W-04 late-locator queue semantics except
  where their status/error mapping must be preserved.
- Adding a new persistence authority or writing raw transcript content to
  telemetry.

## Contract invariants

1. **Validated event identity is authoritative.** The queue event's resolved
   project ID/root and normalized client/session are the expected identity;
   transcript metadata can only confirm them, never replace them.
2. **No proof, no capture.** If the supported native format cannot provide a
   trustworthy match, processing returns an explicit ownership/degraded
   result before EvidenceStore persistence.
3. **Cross-session and cross-project isolation.** A transcript from another
   session or project, even under the same trusted root, produces zero
   evidence and zero canonical/review effects.
4. **Late-file compatibility.** A missing but otherwise trusted locator keeps
   W-04's retryable behavior; an invalid root/symlink/path remains W-03A's
   fail-closed behavior.
5. **Replay safety.** Replaying a rejected ownership event cannot create a
   later effect unless the same event is revalidated successfully against the
   same identity binding.
6. **Privacy.** Persistent diagnostics are content-free and bounded; no raw
   prompt, transcript line, token, or full private path is emitted.
7. **Canonical authority unchanged.** All successful effects continue through
   the existing evidence/extraction/truth worker path; this package adds no
   write path.

## Required tests and evidence

### Focused ownership cases

- Matching Claude session locator/metadata is accepted and captures exactly
  once.
- Matching Codex session locator/metadata is accepted and captures exactly
  once.
- Foreign session under the same trusted root is rejected before evidence
  persistence.
- Foreign project binding is rejected before evidence persistence.
- Missing/unknown identity metadata returns a bounded fail-closed result, not
  a guessed project or session.
- Missing transcript remains W-04 retryable; malformed or mismatched identity
  is not an infinite retry loop.
- Symlink/traversal and configured-root checks remain W-03A behavior.
- Replay of an ownership rejection produces no effect; accepted replay keeps
  existing evidence idempotence.
- Diagnostics contain only bounded codes/hashes and no raw content/full path.
- Replacing a transcript after ownership validation, including a same-size
  replacement, is detected by the stable file-identity check and produces no
  evidence.

### Regression and review gates

1. **Identity/provenance gate:** the event identity tuple and ownership
   adapter are tested for both native clients and exact mismatch codes.
2. **Boundary gate:** a static/read-only check shows the ownership check runs
   before `EvidenceStore.persist`, extraction, review, or canonical apply.
3. **Parity/safety gate:** existing W-03A/W-04/W-05 and runtime suites pass
   unchanged; cross-session/project leakage is hard-zero.
4. **Full verification:** complete test suite, critical flake8 (`E9,F63,F7,F82`),
   compile/import sanity, and `git diff --check` pass on the exact revision.
5. **Independent review:** a read-only reviewer checks the contract, diff,
   native-format evidence, failure mapping, privacy, and rollback/replay
   behavior. Only `SHIP`, `FIX-FIRST`, or `RETHINK` is valid; self-review is
   not acceptance.

## Acceptance thresholds

- cross-session leakage: **0**
- cross-project leakage: **0**
- ownership mismatch canonical/review effects: **0**
- accepted replay duplicate effects: **0**
- W-03A/W-04/W-05 regression: **0**
- all focused and full verification gates: **PASS**
- independent review: **SHIP**

## Queue outcome matrix

| Condition | Error/status | Retry | Canonical/evidence effect |
|---|---|---:|---:|
| Trusted locator temporarily missing | `TRANSCRIPT_NOT_FOUND` / existing degraded path | yes, bounded by queue attempts | none until a later successful validation |
| Root/traversal/symlink violation | existing W-03A provenance code | no; dead-letter | zero |
| Session or project mismatch | `TRANSCRIPT_OWNERSHIP_MISMATCH` | no; dead-letter | zero |
| Required identity metadata absent/unknown | `TRANSCRIPT_OWNERSHIP_UNVERIFIED` | no; dead-letter | zero |
| File replaced/changed during validation/read | `TRANSCRIPT_CHANGED` | yes, bounded by queue attempts | zero for failed attempt |

The exact code and terminal state must be recorded in the queue ledger without
raw content or full paths. A terminal ownership failure must never be hidden
as a successful `PROCESSED` receipt.

## Package report template

`PACKAGE`, `REVISION`, `OBJECTIVE`, `FILES CHANGED`, `ROOT CAUSES
ADDRESSED`, `TESTS ADDED`, `TESTS EXECUTED`, `QUALITY METRICS BEFORE`,
`QUALITY METRICS AFTER`, `SAFETY METRICS`, `KNOWN LIMITATIONS`, `OPEN
FAILURES`, `INDEPENDENT REVIEW`, `SCORE BEFORE`, `SCORE AFTER`, `VERDICT`.

**Contract status:** REVIEW PENDING — implementation has not started.
