# W-17 Runtime-Owned Path Containment Contract

**Status:** REVIEW PENDING — implementation is not authorized by this document
**Finding:** `brain_eleven/runtime/storage.py::write_json()` follows a
symlinked or Windows reparse-point runtime directory and can publish runtime
state outside the selected vault.
**Priority:** P2 (raise if the runtime directory is writable by an untrusted
process)

## Evidence

At `brain_eleven/runtime/storage.py:20-32`, `write_json()` calls
`path.parent.mkdir()`, creates its temporary file with `mkstemp(dir=path.parent)`
and then calls `os.replace()` without checking existing path components.  A
read-only isolated probe created `vault/.brain-eleven/runtime -> outside/` and
then called `RuntimeConfig(vault).set_human_approval(True)`; the call succeeded
and wrote `outside/config.json`.  A Windows junction produced the same result
while `Path.is_symlink()` remained false and the reparse attribute was set.

The final `config.json` symlink is replaced by `os.replace()` rather than
followed; the vulnerable boundary is the parent directory (and any ancestor),
which also redirects lock and temporary-file creation.  Existing
`scripts/memory_backup.py` already demonstrates the repository's stronger
`lstat()`/reparse, containment, no-follow and identity-check policy.

## Bounded objective

Make writes to the vault-owned runtime tree fail closed when any existing path
component is a symlink or Windows reparse point, and ensure the resolved target
remains inside the selected vault's `.brain-eleven/runtime` directory.  The
existing JSON schema, lock/CAS behavior, temp-file + fsync + replace atomicity,
and caller-visible success/error semantics for regular paths must remain
unchanged.

The guard must run before directory creation, lock-file creation, temporary-file
creation, or replacement.  A rejected path must leave the vault and any outside
target unchanged, including no external `config.json`, `.lock`, or temp file.

## Required design

1. Add a small runtime-path safety primitive using the existing backup policy as
   prior art.  It must inspect each existing component with `lstat()` and, on
   Windows, reject `st_file_attributes & 0x400` (reparse point) even when
   `Path.is_symlink()` is false.  Missing final files remain creatable; missing
   parent components may be created only after all existing ancestors pass.
2. Resolve and contain runtime-owned destinations under the canonical vault
   runtime root.  Reject `..` escapes, alternate-drive paths, and any resolved
   destination outside `vault/.brain-eleven/runtime`.
3. Apply the guard at operation time, before `RuntimeConfig` locks and before
   `write_json()` creates directories or temp files.  Recheck the relevant path
   identity after temp creation and before replacement; if the platform cannot
   guarantee a race-safe no-follow operation, fail closed rather than claiming
   containment.
4. Preserve final-file behavior explicitly: a final `config.json` symlink must
   never be followed or mutated; either replace it safely inside the validated
   runtime directory or reject it, with tests fixing the chosen behavior.
5. Keep `RuntimeConfig.set_mode()`, `set_human_approval()`, and the installer’s
   `_mutate_current()` update on the same guarded writer.  All other writes
   whose destination is below `RuntimeConfig.root` (worker, launcher, review,
   maintenance, service, graduation and telemetry artifacts) must receive the
   same guard through the shared runtime writer or an explicit adapter; no
   runtime-owned caller may silently bypass it.
6. Host Claude/Codex configuration files and their install/uninstall policy are
   a separate host-filesystem concern.  They may use a shared no-follow check,
   but this package must not apply vault containment to host paths or change
   hook/manifest ownership semantics.
7. Do not change canonical `MemoryStore`, `StateStore`, `ProjectRegistry`,
   capture, retrieval, V2, or Phase 20 behavior.  Do not add a new persistence
   authority or schema field.

## Invariants

- Regular runtime paths preserve JSON bytes, atomic replace, fsync, lock and
  W-15 fingerprint/CAS behavior.
- Existing `.brain-eleven`/`runtime` directories are accepted only when their
  components are regular directories; symlink/reparse redirection is rejected.
- Vault, runtime root, lock path and temporary path remain within the same
  resolved runtime containment root.
- A path swap between validation and publish cannot redirect a write silently;
  the operation fails closed or proves the opened directory/file identity.
- Error reporting is bounded and content-free; no prompt, token, memory or
  private config content is emitted.
- Existing non-runtime `write_json()` callers retain their current schema and
  atomic semantics; only unsafe link/reparse destinations are rejected.

## Required tests and evidence

### Safety and race cases

- runtime directory symlink: setter and direct runtime artifact write reject;
  outside config/lock/temp files do not appear;
- `.brain-eleven` ancestor symlink: reject before any external effect;
- Windows junction/reparse directory: reject even when `is_symlink()` is false;
- final `config.json` symlink: chosen replace/reject behavior is deterministic
  and outside target remains unchanged;
- `..`/alternate-drive escape and path swap during validation/publish: reject or
  prove identity, never silently redirect;
- missing regular runtime directories: create and write as before;
- regular `RuntimeConfig` mode/approval updates preserve W-15 CAS conflict,
  lock timeout and atomic-write tests;
- runtime worker/launcher/review/maintenance/service telemetry writes use the
  same guard; no caller bypass remains by AST/caller inventory.

### Regression and scope gates

1. Identity: public package/legacy `RuntimeConfig`, `write_json` and any new
   typed error remain the same objects across documented surfaces.
2. Adapter/caller audit: all runtime-owned write callers are enumerated and
   either use the guarded writer or are explicitly out of scope with evidence.
3. Parity+safety: existing W-15, W-08B, runtime, install, launcher, worker,
   review and maintenance tests pass unchanged; new symlink/junction/escape
   tests pass.
4. Full verification: `pytest tests -q`, critical flake8
   (`E9,F63,F7,F82`), `compileall`, and `git diff --check` on the exact head.
5. Independent read-only review: reviewer checks the contract, diff, platform
   behavior, race evidence, caller coverage and absence of canonical authority
   changes.  The verdict is exactly `SHIP`, `FIX-FIRST`, or `RETHINK`.

## Acceptance gate

W-17 remains open until regular-path parity, runtime-root containment,
symlink/reparse rejection (including Windows junction), no-external-effect
evidence, and independent `SHIP` are all present.  A passing unit suite without
native Windows junction evidence does not close the package.

## Estimated diff

Contractual estimate: **120–260 production LOC**, **120–220 test LOC**, plus
package report and independent-review evidence.  The implementation may be
smaller if the existing no-follow primitives can be safely factored without
duplicating authority; no unrelated cleanup is authorized.

## Package report template

`PACKAGE`, `REVISION`, `OBJECTIVE`, `FILES CHANGED`, `ROOT CAUSES ADDRESSED`,
`TESTS ADDED`, `TESTS EXECUTED`, `QUALITY METRICS BEFORE`, `QUALITY METRICS
AFTER`, `SAFETY METRICS`, `KNOWN LIMITATIONS`, `OPEN FAILURES`, `INDEPENDENT
REVIEW`, `SCORE BEFORE`, `SCORE AFTER`, `VERDICT` (`SHIP`/`FIX-FIRST`/`RETHINK`).

**Plan status: REVIEW PENDING — implementation başlamadı.**
