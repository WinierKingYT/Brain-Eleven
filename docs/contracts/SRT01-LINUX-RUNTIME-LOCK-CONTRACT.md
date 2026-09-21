# SRT-01 — POSIX Runtime Lock Context-Manager Contract

**Status:** REVIEW PENDING — implementation is not authorized by this document
**Program:** Stabilization & Runtime Truth
**Package:** SRT-01 Linux runtime lock protocol repair
**Priority:** CI correctness / runtime durability
**Contract baseline:** `48d40f64c38e9b10afdfb4615fc5099d9e707d50`
**Phase 20:** FROZEN / LOCKED

## Finding and evidence

`brain_eleven/runtime/storage.py` imports `contextmanager` at line 7. The
private `_runtime_posix_lock()` generator is defined at lines 36–86 and yields
at line 78, but has no `@contextmanager` decorator. `runtime_file_lock()` is
itself a context manager at lines 118–141 and enters that generator with
`with` at line 139:

```python
@contextmanager
def runtime_file_lock(target, timeout=10.0, poll_interval=0.05):
    ...
    else:
        with _runtime_posix_lock(runtime_root, target, snapshot, timeout, poll_interval):
            ...
```

On Ubuntu, this produces the confirmed exception:
`TypeError: 'generator' object does not support the context manager protocol`.
The exact signature repeats in PRE-13 runtime run `35127040619`, job
`104898515102` (57 failed tests), and Validation run `35127040607`, job
`104898515132` (120 of 130 unit failures). The same failure is present in the
historical runs `35126442602`/`35126442600`. The Windows helper is separately
decorated at lines 88–116 and does not take this failing path.

The defect is therefore a protocol boundary omission, not a request to change
lock identity, timeout policy, path containment, or persistence semantics.

## Bounded objective

Make `_runtime_posix_lock()` usable as the context manager already required by
`runtime_file_lock()`. The permitted implementation is to apply the existing
`contextlib.contextmanager` decorator immediately above `_runtime_posix_lock()`
at the current line-36 boundary. The generator body, its `yield`, and all
cleanup paths must remain behaviorally unchanged.

This package closes only the Linux context-manager protocol failure. It does
not make a claim that the complete Validation or PRE-13 workflows will become
green; the separately tracked failures below remain visible and must not be
masked by this package.

## Allowed change surface

- `brain_eleven/runtime/storage.py`: the decorator needed to adapt the existing
  `_runtime_posix_lock()` generator to the context-manager protocol.
- A focused SRT-01 regression test file, or narrowly scoped additions to the
  existing runtime-lock tests, covering the public `runtime_file_lock()`
  behavior on POSIX.
- This contract and the package evidence report.

No other production module, workflow, threshold, marker naming rule, lock
algorithm, or public API change is authorized. The existing import at line 7
must be reused; a second locking abstraction is not permitted.

## Required invariants

1. `runtime_file_lock(target, timeout=10.0, poll_interval=0.05)` keeps the same
   callable signature and remains a context manager for both POSIX and
   Windows.
2. POSIX acquisition still opens the validated runtime root once, verifies
   the captured identity, creates the target-specific marker relative to the
   root descriptor, acquires the per-target thread lock, and uses
   `fcntl.flock(..., LOCK_EX | LOCK_NB)` with the existing timeout and polling
   behavior.
3. Normal exit, an exception from the context body, acquisition timeout, and
   validation failure all release the same resources already released by the
   `finally` blocks at lines 79–85. No descriptor, thread lock, or OS flock may
   remain held after the operation returns or raises.
4. The lock remains per target: distinct targets may proceed concurrently, and
   equivalent lexical aliases continue to map to the same lock key through
   `_runtime_lock_key()`.
5. The target-specific marker remains internal to the validated runtime root;
   no raceable `target.lock` sidecar is introduced. Snapshot checks before and
   after acquisition remain in place at lines 128–140.
6. The Windows `_runtime_windows_mutex()` branch and its behavior remain
   unchanged. The fallback `_base_file_lock()` path for targets without a
   runtime root remains unchanged.
7. All current callers continue to use the existing `runtime_file_lock` / `file_lock`
   alias. No caller is moved to a new lock surface.
8. Error classes, timeout messages, JSON bytes, atomic writes, path-containment
   checks, and canonical MemoryStore/StateStore authority remain unchanged.
9. Failure evidence remains bounded and content-free. No prompt, transcript,
   memory, or private configuration content may be added to logs or reports.

## Focused tests and evidence

The focused tests must exercise the real POSIX branch on `ubuntu-latest`; they
must not monkeypatch the platform selector or add a skip that hides the branch.
The same public tests should also run on `windows-latest` to preserve mutex
parity.

### New SRT-01 regression

Add only the smallest meaningful test coverage, for example in
`tests/test_srt01_runtime_lock.py`:

- acquire `runtime_file_lock()` for an isolated runtime target, enter the body,
  and acquire it again after normal exit;
- raise from inside the lock body, then reacquire the same target to prove the
  existing cleanup path releases the POSIX flock and descriptors;
- use a distinct target while the first target is held to preserve the
  per-target independence invariant.

The tests must assert observable lock behavior through `runtime_file_lock()`;
they must not merely assert that a decorator exists.

### Existing focused regression

Run these unchanged tests on both matrix operating systems, with the POSIX
execution of the command occurring on Ubuntu:

```text
pytest -q tests/test_w17_runtime_path_containment.py \
  -k "runtime_lock or distinct_runtime_targets or lock_key_normalizes"
```

The selected tests cover the external-marker race guard, absence of a
raceable sidecar marker, distinct-target concurrency, and lexical lock-key
normalization. The focused SRT-01 test command and the selected W-17 tests must
complete without the context-manager `TypeError`.

## Regression gates

1. Run the exact PRE-13 runtime command from
   `.github/workflows/runtime.yml` on Ubuntu and Windows, retaining its
   existing test selection, `--cov=brain_eleven/runtime`, and
   `--cov-fail-under=80`. The report must show zero lock-protocol failures and
   no new Windows mutex regressions. A remaining coverage failure or unrelated
   test failure is reported separately; it is not waived or relabeled.
2. Run the exact Validation unit command from
   `.github/workflows/test.yml` on Ubuntu and Windows. Lock-derived failures
   must disappear or reduce to a separately evidenced cause. The W-03B and
   Windows-only failures listed under **Out of scope** remain explicit if they
   persist.
3. Run the focused tests above, Python compilation for the touched module and
   `git diff --check`. Do not alter workflow gates to obtain a pass.
4. Repeat the relevant remote workflows at the implementation SHA. Record the
   OS, Python version, job IDs, test identities, and bounded exception classes;
   do not claim the whole workflow is green solely because this package’s
   lock errors are gone.

## Rollback

If the focused POSIX tests fail, a Windows mutex test regresses, or any caller
shows a changed timeout/resource/error contract, revert only the SRT-01
production/test diff to the pre-package SHA and preserve the evidence. Do not
repair the rollback by changing thresholds, adding skips, renaming markers, or
altering path guards. A rollback leaves SRT-01 open and keeps the original
Ubuntu `TypeError` visible until a new bounded implementation is reviewed.

## Explicitly out of scope

The following findings are not SRT-01 work and must not be changed, skipped,
lowered, or used as evidence that this package is complete:

- PRE-13 quality `STALE_INPUT` from the registry-revision mismatch between
  authority selection and `CompilerSnapshot`;
- the PRE-13 Windows coverage result of 65.57% against the existing 80% gate,
  and the Ubuntu coverage drop caused by the current failures;
- W-03B newline/byte-size fixture assertions (`120 == 119` and `119 == 118`);
- Windows `MemoryBackupError` from the final-handle containment check;
- Windows direct `scripts/task_model.py` adapter subprocess exit status 1;
- changes to W-15 configuration CAS, W-17 path-containment policy, W-19B
  health semantics, W-07B recovery semantics, installer/client hooks, or any
  other feature behavior;
- canonical memory/state schemas, V2 promotion, Phase 20, security policy,
  dependency versions, or CI runner configuration.

W-15, W-19B, and W-07B identities that currently fail only because POSIX lock
acquisition raises are useful post-change regression signals. If any such
identity still fails after the protocol repair, its remaining cause requires a
separate investigation and contract.

## Acceptance gate

SRT-01 may be marked **SHIP** only when the reviewed implementation proves the
POSIX context-manager behavior, cleanup, per-target locking, path-safety
ordering, and Windows parity through the focused evidence above. The package
must report any remaining workflow failures under their own causes. A passing
focused test does not authorize threshold changes, skips, Phase 20 promotion,
or closure of SRT-00’s other findings.

## Package report template

`PACKAGE`, `REVISION`, `OBJECTIVE`, `FILES CHANGED`, `ROOT CAUSE ADDRESSED`,
`TESTS ADDED`, `TESTS EXECUTED`, `REMOTE JOB IDS`, `QUALITY METRICS BEFORE`,
`QUALITY METRICS AFTER`, `LOCK/RESOURCE EVIDENCE`, `KNOWN LIMITATIONS`,
`OUT-OF-SCOPE FAILURES`, `ROLLBACK`, `INDEPENDENT REVIEW`, and `VERDICT`
(`SHIP`/`FIX-FIRST`/`RETHINK`).

**Plan status: REVIEW PENDING — implementation has not started.**
