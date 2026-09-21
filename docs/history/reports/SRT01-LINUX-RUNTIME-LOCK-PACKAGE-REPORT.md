# SRT-01 — POSIX Runtime Lock Package Report

**Package:** SRT-01 Linux runtime lock protocol repair
**Contract:** [SRT01-LINUX-RUNTIME-LOCK-CONTRACT.md](SRT01-LINUX-RUNTIME-LOCK-CONTRACT.md)
**Implementation SHA:** `335b6df7dd895b868cb32c1f50e81fa8f8568e55`
**Test SHA:** `f0866b69a2645e90e29fa87034da2688fb15d6fa`
**Pre-package SHA:** `e6ecd1407b07d9ecb381751216a647b63e870238`
**Status:** SHIPPED
**Verdict:** SHIP — SRT-01 only

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

The same Ubuntu-24.04 WSL environment then ran the focused pytest command
with the repository requirements installed into an isolated temporary target:

```text
PYTHONPATH=/tmp/srt01-pydeps:/mnt/c/Users/faruk/Documents/Brain-Eleven \
python3 -m pytest -q tests/test_srt01_runtime_lock.py \
  tests/test_w17_runtime_path_containment.py \
  -k "runtime_lock or distinct_runtime_targets or lock_key_normalizes"
9 passed, 16 deselected in 1.81s
```

This is a real POSIX `fcntl` runner check on Ubuntu 24.04 WSL; GitHub's
`ubuntu-latest` unit matrix also ran the same tests as part of its full unit
command, with no SRT-01 identity in its failure annotations.

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
per-target behavior. Exact-head GitHub Actions evidence is now available. The
Validation run `35133592063` (head `e117893`) still fails only on the reported
W-03B Ubuntu fixture identities and the two Windows identities
`test_direct_adapter_and_package_cli_have_the_same_contract` and
`test_disaster_drill_rebuilds_context_without_cross_project_leakage`; no
POSIX-lock `TypeError` appears in its failure annotations. PRE-13 run
`35133591987` (head `e117893`) still fails its runtime and quality jobs, but
the runtime annotations contain no POSIX-lock `TypeError`; the quality job
retains the historical holdout failure. The report-only follow-up head
`7db5e64` reproduced the same bounded identities in Validation run
`35134323509` and PRE-13 run `35134323406`; its runtime annotations likewise
contain no POSIX-lock `TypeError`. The next report-only head `3349f7c`
reproduced the same identities in Validation run `35134984200` and PRE-13
run `35134984024`, again with no lock-specific annotation. The current
report-only head `bdb549a` then reached terminal status as Validation run
`35135589646` and PRE-13 run `35135589665`: Validation failed after both unit
jobs completed, retaining only the two W-03B Ubuntu identities and the two
documented Windows identities (task-model CLI parity and MemoryBackup);
PRE-13 failed its Ubuntu and Windows runtime jobs and its quality job still
had no `pre13-holdout.json` artifact. None of these terminal annotations
contains the POSIX-lock `TypeError`. These runs are evidence for the reviewed
implementation and its report-only rechecks, and do not constitute a
whole-workflow green claim.

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
- Protected JUnit artifacts/logs prevent further remote traceback inspection
  without authenticated access; the public annotations expose the failure
  identities above.

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
TESTS EXECUTED: 9 focused pytest tests on Windows and Ubuntu 24.04 WSL; real POSIX fcntl smoke; critical flake8; compileall; diff check; unchanged PRE-13 command
REMOTE JOB IDS: baseline 104896530998, 104898515102, 104896531347, 104898515132; implementation-head Validation run 35133592063 (jobs 104920302310, 104920302391), PRE-13 run 35133591987 (jobs 104920301628, 104920301847, 104920302056); report-only follow-up Validation run 35134323509 (Ubuntu job 104922761215, Windows job 104922761076), PRE-13 run 35134323406 (jobs 104922760481, 104922760571, 104922760209); second report-only Validation run 35134984200 (Ubuntu job 104924998546, Windows job 104924998574), PRE-13 run 35134984024 (jobs 104924997061, 104924996971, 104924996643); current report-only Validation run 35135589646 (head bdb549a, 2 unit jobs complete) and PRE-13 run 35135589665 (head bdb549a, Ubuntu/Windows runtime plus quality complete); public annotations show no POSIX-lock TypeError and retain the out-of-scope failures listed above
QUALITY METRICS BEFORE: Ubuntu PRE-13 57 lock failures / 41.71% coverage; Validation Ubuntu 120 lock failures
QUALITY METRICS AFTER: local focused 9/9; local POSIX smoke PASS; local PRE-13 99 passed, 1 unrelated failure / 65.58% coverage
LOCK/RESOURCE EVIDENCE: normal reuse, body-exception cleanup, timeout cleanup, post-acquisition validation cleanup, and distinct-target entry are covered; POSIX smoke confirms the first, second, and fifth behaviors, while the 9-test host suite covers all five
KNOWN LIMITATIONS: exact-head remote workflows remain red for unrelated coverage, quality, Windows and cold-start/runtime identities; protected JUnit logs are unavailable anonymously; the focused Linux pytest evidence is Ubuntu 24.04 WSL while GitHub ubuntu-latest ran it within the full unit command
OUT-OF-SCOPE FAILURES: STALE_INPUT, coverage threshold, W-03B, MemoryBackup, task-model, and other unrelated identities
ROLLBACK: revert f0866b6, 498e72b, and 335b6df; preserve the evidence and original gates
INDEPENDENT REVIEW: `SRT01-LINUX-RUNTIME-LOCK-INDEPENDENT-REVIEW.md`, review head `775d0d2`, verdict SHIP for SRT-01 only
SCORE BEFORE: not assigned
SCORE AFTER: SRT-01 bounded lock reliability gate passed; overall runtime score remains governed by SRT-00 failures
VERDICT: SHIP — SRT-01 only
```

**Implementation status:** complete for the approved bounded diff; independent
review returned SHIP for SRT-01 only. Exact-head and terminal report-only
remote evidence is recorded above, with out-of-scope failures retained rather
than hidden.
