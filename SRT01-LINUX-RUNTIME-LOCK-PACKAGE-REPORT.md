# SRT-01 — POSIX Runtime Lock Package Report

**Package:** SRT-01 Linux runtime lock protocol repair
**Contract:** [SRT01-LINUX-RUNTIME-LOCK-CONTRACT.md](SRT01-LINUX-RUNTIME-LOCK-CONTRACT.md)
**Implementation SHA:** `335b6df7dd895b868cb32c1f50e81fa8f8568e55`
**Test SHA:** `f0866b69a2645e90e29fa87034da2688fb15d6fa`
**Pre-package SHA:** `e6ecd1407b07d9ecb381751216a647b63e870238`
**Status:** REVIEW PENDING
**Verdict:** REVIEW PENDING — not SHIP

## Objective and root cause addressed

The POSIX runtime lock generator in
`brain_eleven/runtime/storage.py::_runtime_posix_lock()` was entered with
`with` by `runtime_file_lock()` but lacked the existing `contextlib.contextmanager`
decorator. Ubuntu therefore raised
`TypeError: 'generator' object does not support the context manager protocol`.

The implementation adds exactly one line, `@contextmanager`, immediately above
`_runtime_posix_lock()` at the line-36 boundary. The generator body, lock
algorithm, marker name, timeout/polling behavior, path checks, and cleanup
blocks are unchanged. No workflow, threshold, skip, or unrelated production
file was changed.

## Files changed

- `brain_eleven/runtime/storage.py`: one decorator line.
- `tests/test_srt01_runtime_lock.py`: five focused behavior tests.
- This package report.
- `SRT00-BASELINE-FAILURE-REPRODUCTION.md`: coverage-gate boundary clarification.

## Tests and checks executed

The focused host command exercised the five new tests and the four existing
W-17 runtime-lock tests:

```text
python -m pytest -q tests/test_srt01_runtime_lock.py tests/test_w17_runtime_path_containment.py -k "runtime_lock or distinct_runtime_targets or lock_key_normalizes"
9 passed, 16 deselected in 0.82s
```

The available Ubuntu-24.04 WSL image ran a direct POSIX smoke against the real
`fcntl` path (Python 3.12.3). It passed acquisition, normal reuse, body
exception cleanup followed by reacquisition, and distinct-target concurrent
entry:

```text
SRT01 POSIX smoke: PASS
```

The requested static checks passed:

```text
python -m flake8 scripts context_router authority context_compiler_v2 retrieval_decision_v2 context_density_v2 evals tests --count --select=E9,F63,F7,F82 --show-source --statistics
0

python -m compileall -q brain_eleven/runtime/storage.py tests/test_srt01_runtime_lock.py
PASS

git diff --check
PASS
```

The unchanged PRE-13 command was also run locally on Windows with the
workflow's existing `--cov-fail-under=80`. It produced **99 passed, 1 failed**
and **65.58%** coverage. The one failure was the unrelated
`test_cold_native_session_start_delivers_v1_within_hook_budget` assertion
(`KeyError: 'hookSpecificOutput'`); no lock protocol `TypeError` occurred. The
job still failed its unchanged 80% coverage gate.

## Before and after evidence

Before this package, the investigated Ubuntu jobs reported the same lock
protocol failure:

- PRE-13 `35126442602` job `104896530998` and `35127040619` job `104898515102`:
  57 runtime test failures, all with the POSIX lock `TypeError`.
- Validation `35126442600` job `104896531347` and `35127040607` job
  `104898515132`: 130 unit failures, including 120 lock-protocol failures.

The local WSL smoke and the focused tests show that the approved decorator
restores the public context-manager boundary and the existing cleanup and
per-target behavior. Exact post-push GitHub Actions evidence at the
implementation SHA is still pending; this report makes no whole-workflow
green claim.

## Scope confirmation

The package is limited to the POSIX context-manager protocol defect. The
Windows mutex branch, fallback lock path, public `runtime_file_lock` signature,
and all caller aliases are unchanged. No threshold or skip was added, removed,
or modified.

## Known out-of-scope failures and limitations

These findings remain separate and are not repaired or waived by SRT-01:

- PRE-13 quality `STALE_INPUT` caused by the registry-revision mismatch between
  authority selection and `CompilerSnapshot`.
- PRE-13 Windows coverage at 65.57% against the unchanged 80% threshold, and
  the Ubuntu coverage impact from its earlier failures.
- W-03B Ubuntu newline/byte-size assertions (`120 == 119` and `119 == 118`).
- Windows `MemoryBackupError` from the final-handle containment check.
- Windows direct `scripts/task_model.py` adapter subprocess exit status 1.
- Any remaining W-15, W-19B, W-07B, cold-start, installer, or service behavior
  failures after lock acquisition is repaired.
- No authenticated post-push remote run had completed when this report was
  written.

## Regression and rollback

The focused POSIX and Windows-parity tests, critical flake8, compilation, and
diff checks passed. The unchanged PRE-13 command still exposes its existing
coverage gate and one local cold-start failure, as required by the contract.

If remote or focused regression evidence shows a changed timeout, error,
resource-release, marker, path-safety, or Windows mutex contract, revert only
the SRT-01 implementation and test commits (`335b6df`, `498e72b`, and `f0866b6`) to restore
the pre-package code at `e6ecd14`. Do not alter workflows, thresholds, skips,
markers, or unrelated fixes during rollback.

## Package report fields

```text
PACKAGE: SRT-01 Linux runtime lock protocol repair
REVISION: implementation 335b6df7dd895b868cb32c1f50e81fa8f8568e55; tests f0866b69a2645e90e29fa87034da2688fb15d6fa
OBJECTIVE: Adapt the existing POSIX runtime lock generator to the context-manager protocol
FILES CHANGED: one storage decorator, one focused test file, this report, and the SRT00 coverage-boundary clarification
ROOT CAUSE ADDRESSED: missing @contextmanager on _runtime_posix_lock
TESTS ADDED: five behavioral tests for reuse, exception cleanup, timeout cleanup, post-acquisition validation cleanup, and distinct-target concurrency
TESTS EXECUTED: 9 focused pytest tests; Ubuntu WSL POSIX smoke; critical flake8; compileall; diff check; unchanged PRE-13 command
REMOTE JOB IDS: baseline 104896530998, 104898515102, 104896531347, 104898515132; post-push run 35131684181/35131684240 at the pre-review-remediation report head; exact current-head result pending
QUALITY METRICS BEFORE: Ubuntu PRE-13 57 lock failures / 41.71% coverage; Validation Ubuntu 120 lock failures
QUALITY METRICS AFTER: local focused 9/9; local POSIX smoke PASS; local PRE-13 99 passed, 1 unrelated failure / 65.58% coverage
LOCK/RESOURCE EVIDENCE: normal reuse, body-exception cleanup, timeout cleanup, post-acquisition validation cleanup, and distinct-target entry are covered; POSIX smoke confirms the first, second, and fifth behaviors, while the 9-test host suite covers all five
KNOWN LIMITATIONS: post-push remote verification pending; unrelated coverage, quality, Windows and cold-start failures remain
OUT-OF-SCOPE FAILURES: STALE_INPUT, coverage threshold, W-03B, MemoryBackup, task-model, and other unrelated identities
ROLLBACK: revert f0866b6, 498e72b, and 335b6df; preserve the evidence and original gates
INDEPENDENT REVIEW: contract SHIP; implementation review pending
SCORE BEFORE: not assigned
SCORE AFTER: not assigned pending independent review
VERDICT: REVIEW PENDING
```

**Implementation status: complete for the approved bounded diff; independent
review and exact post-push CI evidence remain pending.**
