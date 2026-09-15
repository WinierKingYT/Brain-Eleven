# W-17 Runtime-Owned Path Containment Package Report

**PACKAGE:** W-17
**REVISION:** `6302f30bd7a2c0abddaf22d2d9a4c1cd30b0b5b4`
**STATUS:** REVIEW PENDING

## OBJECTIVE

Prevent vault-owned `.brain-eleven/runtime/**` writes and locks from following
symlinked or Windows reparse-point path components into an outside directory,
while preserving regular-path JSON atomicity and W-15 runtime-config
lock/CAS behavior.

## FILES CHANGED

- `brain_eleven/runtime/path_safety.py` — shared runtime path guard,
  containment and identity snapshot primitive;
- `brain_eleven/runtime/storage.py` — guarded runtime writer/lock integration,
  config-load validation and safe root creation;
- `brain_eleven/runtime/install.py`, `launcher.py`, `maintenance_delivery.py`,
  `migration.py`, `review.py`, `service.py`, `worker.py` — runtime-owned lock
  and directory bootstrap callers routed through the guard;
- `scripts/memory_store_lock.py` — unchanged canonical legacy lock surface;
- `tests/test_w17_runtime_path_containment.py` — safety and parity coverage;
- W-17 contract and independent contract-review evidence documents.

Host Claude/Codex configuration ownership, canonical MemoryStore/StateStore/
ProjectRegistry implementations, capture/retrieval, V2 and Phase 20 were not
changed.

## ROOT CAUSE ADDRESSED

`write_json()` previously called `mkdir`, `mkstemp(dir=path.parent)` and
`os.replace()` without checking path components.  An isolated vault with
`.brain-eleven/runtime` redirected by symlink or Windows junction therefore
accepted `RuntimeConfig.set_human_approval()` and wrote `config.json`, lock and
temporary state outside the vault.

## IMPLEMENTATION

The new path-safety module checks existing components with `lstat()`, rejects
symlinks and Windows `FILE_ATTRIBUTE_REPARSE_POINT`, creates missing regular
ancestors one component at a time, validates lexical/resolved containment,
rejects final-file links and path escapes, and records root/parent identities.
Runtime writes revalidate the snapshot before replacement. Runtime-owned locks
use target-scoped POSIX directory/file locks or Windows named mutexes, so no
raceable sidecar marker is created; direct hook bootstrap paths use the same
wrapper. The existing JSON temp-file flush/fsync/replace path and W-15
fingerprint/CAS semantics remain intact for regular paths.

## TESTS ADDED

`tests/test_w17_runtime_path_containment.py` covers:

- runtime and `.brain-eleven` ancestor symlink rejection with zero external
  config/lock/temp effects;
- final `config.json` symlink rejection and target preservation;
- `..` escape rejection;
- missing regular and nested vault parent creation parity;
- regular atomic JSON write behavior;
- parent replacement/path-swap detection before publication;
- Windows junction/reparse rejection;
- runtime snapshot identity mismatch detection;
- selected-vault validation, runtime-root creation and lock-boundary race
  probes, including the no-sidecar-marker guarantee.

## TESTS EXECUTED

- W17 plus W15, IG-00 bootstrap, PRE-13 runtime, W-07B maintenance delivery
  and capture provenance surfaces: **118 passed, 2 warnings**; the W17-only
  set is **18 passed**.
- Full suite at exact revision `6302f30`: **1262 passed, 2 warnings** in
  291.14 seconds.
- Critical flake8 (`E9,F63,F7,F82`) on all touched Python files: **PASS**.
- `compileall` on all touched Python files: **PASS**.
- `git diff --check`: **PASS**.

## QUALITY METRICS BEFORE / AFTER

Before: runtime parent symlink/junction redirection wrote a successful
approval update outside the vault.  After: runtime-owned link/reparse paths,
ancestor links, escapes and publication-time swaps fail closed; regular paths
retain the previous JSON and recursive-directory behavior.

## SAFETY METRICS

- External config/lock/temp effect on covered rejection paths: **0**.
- Runtime root containment: enforced before directory/lock/temp creation and
  revalidated before replacement.
- Windows junction/reparse attribute: explicitly checked, including the case
  where `Path.is_symlink()` is false.
- W-15 lock/CAS/atomic parity: existing tests pass; no canonical authority
  path changed.
- Privacy: path errors are bounded and do not emit prompt, memory, token or
  config contents.

## KNOWN LIMITATIONS

- Host Claude/Codex configuration files remain a separate host-filesystem
  policy and are not given vault containment semantics by this package.
- The platform race guard uses pre/post component identity checks; environments
  that cannot prove no-follow publication fail closed rather than claim a
  stronger guarantee.
- Existing FastAPI/Starlette dependency deprecation warnings remain.

## OPEN FAILURES

No W-17 focused or full-suite failures remain at this head.  Independent
read-only implementation review is pending.  W-07B remains
`FIX-FIRST / NOT ACCEPTED`, W-12A remains open, and W-18 remains queued.  Phase
20 is still `FROZEN / LOCKED`; V2 remains `SHADOW`.

## INDEPENDENT REVIEW

**PENDING.** A separate reviewer must inspect the exact diff, caller coverage,
POSIX/Windows path behavior, no-external-effect evidence, regular-path parity,
and preservation of lock/CAS/atomic/canonical authority boundaries.  The final
verdict must be exactly `SHIP`, `FIX-FIRST`, or `RETHINK`.

## SCORE BEFORE / AFTER

Scope/fail-closed safety: **8.2 → pending independent review**
Persistence/concurrency: **8.0 → pending independent review**
Runtime path containment: **symlink/reparse redirect possible → bounded
fail-closed guard**

## VERDICT

**REVIEW PENDING** — implementation and evidence are pushed at the exact
revision above; no self-issued SHIP decision is made.
