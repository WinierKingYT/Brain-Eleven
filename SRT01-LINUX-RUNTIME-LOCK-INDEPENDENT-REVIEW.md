# SRT-01 — POSIX Runtime Lock Independent Review

**Review type:** fresh, read-only final implementation/evidence review

**Review head:** `775d0d255f8b9881ddfac085319a1101c78b92cf`

**Implementation/test commits:** `335b6df7dd895b868cb32c1f50e81fa8f8568e55` / `f0866b69a2645e90e29fa87034da2688fb15d6fa`

**Verdict:** **SHIP** for SRT-01 only

## Scope

This review covers only the bounded POSIX runtime-lock protocol repair. It does
not reopen PRE-13 quality or coverage, W-03B, task-model CLI, MemoryBackup,
SRT-00, or any other separately tracked failure.

## Implementation review

The production diff from pre-package revision `e6ecd14` through the reviewed
tree is exactly one insertion at
`brain_eleven/runtime/storage.py:36`:

```text
@contextmanager
```

The existing `contextlib.contextmanager` import is reused. The generator body
and its descriptor-relative marker creation, root identity check, per-target
thread lock, nonblocking `fcntl.flock`, timeout/polling, yield, unlock, and
descriptor cleanup remain unchanged. `runtime_file_lock()` still performs the
same pre- and post-acquisition snapshot checks, Windows mutex branch, fallback
lock path, signature, and aliases. No workflow, threshold, skip, API, marker,
path policy, or unrelated production change is present.

The test commit adds five public-behavior tests covering normal reuse,
body-exception cleanup, process-level timeout cleanup, post-acquisition
validation-failure cleanup, and distinct-target concurrency.

## Focused evidence

The current Windows focused command was re-run during this review and passed:

```text
.venv\\Scripts\\python.exe -m pytest -q tests/test_srt01_runtime_lock.py tests/test_w17_runtime_path_containment.py -k "runtime_lock or distinct_runtime_targets or lock_key_normalizes"
9 passed, 16 deselected in 0.81s
```

Ubuntu 24.04 WSL (Python 3.12.3, real `fcntl`) ran the direct POSIX smoke and
the exact focused pytest selection in an isolated dependency target:

```text
9 passed, 16 deselected in 1.81s
```

The WSL smoke covered acquisition/reuse, body-exception cleanup and
reacquisition, and distinct-target concurrency. Critical flake8 reported `0`,
compileall passed for the touched module and focused tests, and
`git diff --check` passed. These results prove the context-manager behavior,
cleanup, per-target independence, and Windows parity required by the
focused-evidence gate.

## Remote evidence

The implementation-head Validation run
[35133592063](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/35133592063)
at `e117893` completed with the documented W-03B Ubuntu identities and the
documented Windows task-model CLI and MemoryBackup identities. Its Ubuntu and
Windows unit jobs (`104920302310`, `104920302391`) contain no POSIX-lock
context-manager `TypeError` annotation; the package report records the Ubuntu
unit matrix as executing the same focused tests within its full unit command.

The implementation-head PRE-13 run
[35133591987](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/35133591987)
also contains no POSIX-lock `TypeError` in its runtime annotations. Its
remaining runtime/quality failures and unchanged coverage gate are retained
as separate causes.

The terminal report-only current-head runs recorded by package report commit
`775d0d2` are:

- Validation [35135589646](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/35135589646): both unit jobs completed; failure identities are limited to W-03B on Ubuntu and task-model CLI parity plus MemoryBackup on Windows.
- PRE-13 [35135589665](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/35135589665): runtime/quality/coverage remains red, with no POSIX-lock `TypeError` annotation.

The earlier terminal report-only runs at `7db5e64` and `3349f7c` show the same
bounded no-lock-error outcome. The package report records all remaining
failures without claiming a whole-workflow green result.

## Contract gate assessment

All SRT-01 acceptance conditions are met:

1. POSIX `runtime_file_lock()` now enters the existing generator through the
   approved decorator-only production change.
2. Normal exit, body exception, timeout, and post-acquisition validation
   failure release the existing OS/thread/descriptor resources, with focused
   tests and POSIX smoke evidence.
3. Distinct target locking and lexical lock identity remain covered; the
   internal marker and path-safety ordering remain unchanged.
4. Windows mutex parity passes the same focused public tests.
5. Exact implementation-head and terminal report-only workflow evidence shows
   no SRT-01 lock-protocol failure, while unrelated red jobs remain explicit.
6. Evidence is bounded and content-free; no prompt, transcript, memory, or
   private configuration content was added to reports.

## Out-of-scope failures retained

The following remain visible and are not waived by this verdict:

- PRE-13 quality holdout/`STALE_INPUT` and the unchanged 80% coverage gate;
- W-03B Ubuntu newline/byte-size fixture failures;
- Windows task-model direct-adapter CLI failure;
- Windows MemoryBackup containment failure; and
- other W-15, W-19B, W-07B, cold-start, installer, or service failures not
  caused by the repaired lock protocol.

No threshold, skip, workflow, marker, path guard, canonical store, or Phase
20 change is authorized by this review.

## Final decision

**SHIP — SRT-01 only.** The one-line production repair is bounded, the focused
POSIX and Windows evidence passes, and the exact implementation plus terminal
report-only runs contain no POSIX-lock context-manager failure. Remaining
workflow failures retain their independent causes and require separate work.

No production or status document was modified during this review; this file is
the independent review artifact requested for sign-off.
