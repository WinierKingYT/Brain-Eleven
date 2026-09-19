# W-03A — Transcript Path Confinement Contract

**Status:** BOUNDED CONTRACT / IMPLEMENTATION PENDING  
**Program:** Engineering Weak-Point Improvement Goal  
**Phase 20:** FROZEN / LOCKED  
**V2:** SHADOW

## Objective

Prevent a native capture event from making the evidence reader open an
arbitrary absolute file. A transcript locator is untrusted data. Before a
queue job is created and again before a worker reads it, the canonical path
must be a regular file below the configured client transcript root.

This package addresses the immediate filesystem boundary only. It does not
claim to prove project or session ownership from transcript metadata.

## Current failure

`brain_eleven/runtime/worker.py:102-127` currently calls `Path(source).stat()`
and then queues the locator. `scripts/evidence.py:173-185` rejects relative,
parent-component, symlink and non-file paths, but it has no client-root
containment check. `brain_eleven/runtime/evidence.py:10-91` repeats the generic
file checks without proving that the source belongs to Claude or Codex.

## Bounded implementation

Add one resolver, `scripts/capture_provenance.py`, with these rules:

1. Client identity comes from the trusted `worker.enqueue(..., client, ...)`
   argument. Unknown clients fail closed.
2. Runtime configuration may provide `transcript_roots` as a mapping from
   `claude`/`codex` to non-empty absolute directories. When absent, the
   resolver uses the native local defaults (`~/.claude/projects` and
   `$CODEX_HOME/sessions` or `~/.codex/sessions`). The payload cannot select or
   expand a root.
3. The source must be absolute, resolve strictly, be a regular file, and be
   contained in one configured root after resolution. Parent traversal,
   mixed separators, source symlinks, junction escapes and root escapes fail
   closed with a content-free `TRANSCRIPT_PROVENANCE_*` error.
4. `worker.enqueue` validates before `stat`, event construction, queue write or
   any evidence effect. `worker.process` validates again immediately before
   incremental reading, so relocation/config changes between enqueue and
   processing are rejected.
5. The queue/evidence metadata contract remains content-safe: no raw transcript
   bytes are added to receipts, ledger entries or evidence metadata.

The existing direct `TranscriptReader` API remains generic for offline/manual
evidence tooling; the native runtime boundary is the enforced scope of W-03A.

## Explicitly deferred

- Claude project-slug to registry-root ownership proof.
- Codex session-index/project association (Codex paths do not encode a project).
- Session filename/metadata ownership proof.
- Same-size replacement detection and stable file fingerprint binding.
- Late transcript durability (W-04), prompt event semantics (W-05), queue
  retention, extraction, retrieval, V2 promotion and Phase 20.

These limitations must remain visible in the package report; W-03A must not be
described as complete transcript provenance.

## Acceptance criteria

- Root-contained Claude and Codex files are accepted with configured roots.
- Foreign-root, traversal, alternate-separator, source-symlink, junction and
  missing/non-file paths fail closed before queue creation.
- Enqueue and process both enforce the resolver.
- Project/memory/state/graph files remain unchanged on provenance rejection.
- Existing queue, evidence and IG-02 behavior remains green; test fixtures use
  explicit temporary roots rather than weakening the production boundary.
- Critical flake8 (`E9,F63,F7,F82`), compile/import sanity and `git diff --check`
  pass.
- Independent read-only review returns exactly `SHIP`, `FIX-FIRST` or
  `RETHINK`; self-review is not acceptance.

## Evidence plan

1. Resolver unit matrix for valid roots, traversal, symlink/junction escape,
   wrong client and malformed configuration.
2. Enqueue rejection proves no queue/evidence/canonical effect.
3. Worker revalidation proves a post-enqueue root/config change fails closed.
4. Existing capture/evidence regression suite plus full suite.
5. Independent review of contract, diff, tests and deferred boundaries.

**Package verdict:** REVIEW PENDING until implementation and independent review.
