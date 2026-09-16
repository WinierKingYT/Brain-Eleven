# SRT-00 — Exact Head Failure Reproduction

**Program:** Stabilization & Runtime Truth (proposed)  
**Package:** SRT-00 Baseline Freeze & Failure Reproduction  
**Status:** **FIX-FIRST / NOT ACCEPTED**  
**Exact HEAD:** `9496b3eac39b29a3ad8ceb9b09687ddae4441cd3`  
**Phase 20:** FROZEN / LOCKED  
**V2:** SHADOW

This document records the current release-health evidence. It does not
authorize a feature, runtime, workflow, or architecture change.

## Remote evidence

GitHub Actions Validation run `35084029380` was triggered by a push to
`master` at the exact SHA above on 2026-09-16.

| Job | Result | Evidence |
|---|---|---|
| Unit tests (ubuntu-latest) | FAIL | job `104754493906` |
| Unit tests (windows-latest) | FAIL | job `104754493943` |
| IG01-B corpus integrity | PASS | run `35084029380` |
| IG01-C evaluator/anti-gaming gates | PASS | run `35084029380` |
| Downstream integration, coverage, runtime and security jobs | SKIPPED | blocked by `needs: unit` |

The workflow definition at `.github/workflows/test.yml` installs and runs
Python **3.13** (`setup-python` lines 26–29), while the supplied audit summary
described the run as Python 3.11. The workflow file and run metadata are the
authoritative version evidence.

The public job annotations identify these unit failures:

**Ubuntu** (`104754493906`):

- `tests.test_ig00_bootstrap.test_install_suspends_only_exact_legacy_and_uninstall_restores`
- `tests.test_ig00_bootstrap.test_cold_native_session_start_delivers_v1_within_hook_budget`
- `tests.test_ig00_bootstrap.test_native_bootstrap_flush_receipt_deduplicates[codex]`
- `tests.test_ig00_bootstrap.test_native_bootstrap_flush_receipt_deduplicates[claude]`
- `tests.test_ig00_bootstrap.test_bootstrap_bounded_and_scope_disabled`
- `tests.test_ig00_bootstrap.test_bootstrap_revalidates_after_render[OFF]`
- `tests.test_ig00_bootstrap.test_shadow_bootstrap_is_v1_but_prompt_is_not_delivered[codex]`
- `tests.test_ig00_bootstrap.test_shadow_bootstrap_is_v1_but_prompt_is_not_delivered[claude]`
- `tests.test_capture_provenance.test_late_file_arrival_reuses_one_durable_job`
- `tests.test_capture_provenance.test_worker_revalidates_root_before_evidence_read`

**Windows** (`104754493943`):

- `tests.test_task_model_package_migration.test_direct_adapter_and_package_cli_have_the_same_contract`
- `tests.test_memory_backup.test_disaster_drill_rebuilds_context_without_cross_project_leakage`

The protected JUnit artifacts are not anonymously downloadable; the job page
exposes identities and exit status but not assertion bodies. No raw test
payload or private memory content is copied into this report.

## Local exact-head evidence

The repository was checked out at the same SHA and the workflow's unit command
was run with the local `.venv` interpreter:

```text
.venv\Scripts\python.exe -m pytest tests/ -q --tb=short -m "not integration and not graduation" --junitxml=.w25-ci-unit-local.xml
1354 passed, 4 skipped, 82 deselected, 2 warnings in 292.02s
```

The twelve annotated test identities above were also run directly in one
process and all passed:

```text
14 passed in 8.98s
```

The full local regression at the same exact HEAD (including the W-25 graph
provenance remediation) was:

```text
1436 passed, 4 skipped, 2 warnings in 300.80s
```

## Reproduction disposition

The remote failure is **confirmed**, but its root cause is **not yet known**:
the same test identities pass locally, and the remote assertion bodies are
not available without authenticated artifact access. Therefore SRT-00 has not
met its exit gate.

The current evidence does not justify changing test thresholds, adding skips,
marking tests flaky, or attributing the failures to a specific OS/timing
cause. Native startup latency, filesystem behavior and CI dependency/runtime
differences are hypotheses only until a fresh run exposes bounded failure
details.

## Required next evidence

1. Re-run the exact SHA on both runner images with a content-safe, retrievable
   failure summary (test identity, exception class/code and bounded timing;
   no prompt, transcript or memory payload).
2. Compare runner Python/dependency versions and relevant environment values
   against the local invocation.
3. Reproduce each failure class before changing production or workflow code.
4. Record the first verified root cause and a bounded SRT-01 fix contract.

Until those steps produce a known cause and same-SHA green mandatory gates:

```text
SRT-00 = FIX-FIRST / NOT ACCEPTED
Release disposition = FIX-FIRST
```

## Package report

```text
PACKAGE: SRT-00 Baseline Freeze & Failure Reproduction
REVISION: 9496b3eac39b29a3ad8ceb9b09687ddae4441cd3
OBJECTIVE: Freeze and reproduce current-head CI failures
FILES CHANGED: this evidence document only
ROOT CAUSES ADDRESSED: none yet; remote failures enumerated
TESTS ADDED: none
TESTS EXECUTED: exact workflow unit command, 14 annotated tests, full local regression
QUALITY METRICS BEFORE: current remote Validation = FAIL
QUALITY METRICS AFTER: root cause not established; no quality claim
SAFETY METRICS: no production/runtime mutation
KNOWN LIMITATIONS: authenticated JUnit assertion bodies unavailable
OPEN FAILURES: 12 remote unit failures; downstream gates skipped
INDEPENDENT REVIEW: pending
SCORE BEFORE: build health / release confidence = 2.5/10 (audit estimate)
SCORE AFTER: unchanged pending reproduction
VERDICT: FIX-FIRST / NOT ACCEPTED
```
