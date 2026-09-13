# W-06B Independent Implementation Review

**Revision reviewed:** `21ee199` (`Implement bounded W-06B task-aware V1 retrieval`)
**Review mode:** independent read-only review; package report and implementer reasoning were not treated as evidence.
**Contract:** `WEAKNESS-W06B-TASK-AWARE-RETRIEVAL-CONTRACT.md`

## Evidence executed

- `.venv\Scripts\python.exe -m pytest -q tests/test_w06b_task_aware.py tests/test_ig00_bootstrap.py tests/test_pre13_runtime.py` — **72 passed, 2 warnings**.
- `.venv\Scripts\python.exe -m pytest -q` — **1074 passed, 2 warnings**.
- `.venv\Scripts\python.exe -m flake8 --select=E9,F63,F7,F82 brain_eleven/runtime/storage.py brain_eleven/runtime/context.py brain_eleven/runtime/task_aware.py tests/test_w06b_task_aware.py` — **PASS**.
- `.venv\Scripts\python.exe -m compileall -q brain_eleven/runtime/storage.py brain_eleven/runtime/context.py brain_eleven/runtime/task_aware.py` — **PASS**.
- `git diff --check` — **PASS**.
- A controlled revision-race probe mutated `MemoryStore` during selection; the runtime returned `STALE_INPUT` and did not publish the stale context — **PASS**.
- A direct task-need probe and malformed-gate probe were run against the package implementation — failures below.

The full suite includes the currently untracked `tests/test_w06b_task_aware.py`; that file was not part of reviewed commit `21ee199` and must be committed separately or explicitly accounted for.

## Findings

### F1 — `NO_NEED` and `UNAVAILABLE` do not perform the contract-required legacy fallback (P1, FIX-FIRST)

The contract says `NO_NEED`, `AMBIGUOUS`, `UNAVAILABLE`, and `INVALID` must deterministically use legacy ranking while preserving trusted scope/history. In `brain_eleven/runtime/task_aware.py:67-69`, every non-`READY` result returns an empty context immediately. The exception path at `:99-101` also returns an empty context with provider `V1`, although it never invokes `compile_task` or the legacy ranking path.

Independent probe:

```text
task_need(GENERAL task with no entities/needs) -> NO_NEED
select(legacy compiler containing one eligible memory) ->
  status=NO_NEED, provider=V1, selected=[], context=''
```

This is a behavioral regression for ordinary/general prompts when `W06B_TASK_AWARE` is enabled: the result advertises the legacy provider but omits the legacy context. It also violates the explicit fallback contract and has no focused regression test.

### F2 — Malformed `retrieval_mode` is not fail-closed for non-hashable values (P1, FIX-FIRST)

`brain_eleven/runtime/storage.py:54-58` checks membership directly against a set. A malformed JSON value such as `"retrieval_mode": []` raises `TypeError: unhashable type: 'list'` instead of resolving to `V1_LEGACY` with bounded `RETRIEVAL_MODE_INVALID` telemetry. The contract explicitly requires missing, malformed, unknown, or unreadable gate values to fail closed without a raw configuration exception.

The current focused test covers an unknown string only; it does not cover wrong JSON types (`null`, list, object, number), so this failure was not caught.

### F3 — Required quality and operational evidence is absent (P1, FIX-FIRST)

`W-06B-PACKAGE-REPORT.md` records quality after/before as not measured and says evaluation was blocked/pending. The contract exit gate requires exact V1 baseline and W-06B comparison on the same W-09A DEV/TEST boundary, safety counters, deterministic shuffled-input evidence, budget/mandatory-overflow evidence, and p95 latency over the prescribed repeated runs. The implementation has no such reports or evidence at this revision.

The full suite being green proves regression compatibility only; it does not establish the W-06B quality target or the V1-vs-W06B comparison required by the contract.

### F4 — Task status model is only partially exercised (P2, follow-up required)

`TaskNeedResult` declares `AMBIGUOUS` and `UNAVAILABLE`, but `task_need()` only produces `READY`, `NO_NEED`, and `INVALID`; `AMBIGUOUS` is not resolved by the bounded handoff. The exception path produces `UNAVAILABLE` only after broad exception swallowing. The contract requires bounded handling and tests for malformed task fields, invalid enums/identifiers, and explicit fallback behavior. This should be covered while fixing F1, without broadening the package.

## Safety and boundary review

- No W-06B code writes `MemoryStore`, `StateStore`, or `ProjectRegistry`; the reviewed path reads legacy canonical projections only.
- `SessionStart` still calls `compile_bootstrap`; it does not select W-06B. Focused bootstrap tests passed.
- `UserPromptSubmit` is the only event routed to W-06B when the gate is valid.
- Scope/lifecycle filtering remains delegated to the legacy compiler, with an additional project/secret/capture-safety filter. The controlled source revision race was rejected as `STALE_INPUT`.
- Deterministic ranking has a content fingerprint tie-break and is independent of input order for distinct records; no shuffled-input evidence was supplied.
- Runtime telemetry excludes the rendered context and the task-need structure is serialized as a plain dictionary. The focused privacy test passed.
- V2, embedding-provider migration, Phase 20 promotion, and canonical write authority were not introduced by the reviewed diff.

## Required fixes before re-review

1. Implement and test true legacy fallback for `NO_NEED`, `AMBIGUOUS`, `UNAVAILABLE`, and `INVALID` according to the frozen contract; do not label an empty result as V1 fallback.
2. Make gate parsing type-safe and fail closed for all malformed JSON types while emitting only the bounded invalid-gate code.
3. Add the contract-required W-09A DEV/TEST baseline and W-06B comparison reports, including hard safety counters, deterministic shuffled-input evidence, budget/overflow evidence, and p95 latency evidence. Keep HOLDOUT untouched until the package is otherwise frozen.
4. Add focused tests for wrong-type gate values, general/no-need prompts, provider-unavailable fallback, malformed task input/status handling, and shuffled candidate order.
5. Commit the focused test file and update the package report with exact commands/results. Then rerun independent review on the resulting exact revision.

## Verdict

**FIX-FIRST**

The implementation is regression-green and the source revision guard is effective, but the frozen runtime fallback contract and fail-closed malformed-gate contract are not satisfied, and the required quality/operational acceptance evidence is missing. W-06B must remain open; no score increase, V2 promotion, or Phase 20 work is authorized.

## Re-review — exact current head `06644fa`

The F1/F2 fixes and the evaluation work were reviewed independently again. The
small follow-up at `06644fa` only makes the legacy provider identity explicit;
it does not change the ranking algorithm or the measured quality.

### Re-review evidence

- `pytest -q tests/test_w06b_task_aware.py tests/test_w09a_retrieval_evaluation.py` — **19 passed**.
- The full suite at the preceding exact implementation head `0b665a2` — **1081 passed, 2 warnings**. The only subsequent code change is the provider-label fix in `06644fa`; the focused suite was rerun on that head.
- Critical flake8, compileall and `git diff --check` on the runtime/evaluation surfaces — **PASS**.
- Fresh W-06B DEV and TEST reports were generated with source SHA `06644fa`; corpus/source/candidate fingerprints match the committed evidence.
- DEV and TEST safety counters remain all zero.

### F1/F2 resolution

- Wrong-type gate values (`None`, list, object and number) now resolve to
  `V1_LEGACY` with `RETRIEVAL_MODE_INVALID` telemetry.
- `NO_NEED` fallback now calls the legacy `compile_task` path and returns a
  bounded task status while preserving provider identity `V1`.
- The focused tests cover both changes. These prior blockers are resolved.

### Quality gate result

The frozen contract still fails decisively:

| Split | Provider | Precision | Mandatory recall | MRR | Noise | V1 comparison |
|---|---|---:|---:|---:|---:|---|
| DEV | V1 | 0.165714 | 0.714286 | 0.454524 | 0.834286 | baseline |
| DEV | W-06B | 0.182857 | 0.800000 | 0.448095 | 0.802857 | MRR regresses |
| TEST | V1 | 0.180000 | 0.825000 | 0.491944 | 0.820000 | baseline |
| TEST | W-06B | 0.176667 | 0.841667 | 0.424722 | 0.740000 | precision and MRR regress |

The contract requires precision `>= 0.60`, mandatory recall `>= 0.80`, MRR
non-regression, and W-06B TEST precision strictly above V1. W-06B reaches the
recall floor and reduces noise/token waste, but precision remains roughly
0.18, below the required floor on both splits; TEST precision is below V1 and
TEST MRR is materially worse. This is a quality failure of the current
task-aware ranking approach, not a documentation-only issue.

Operational evidence reports p95 latency and the five-item bound as passing,
and all public safety counters are zero. The package report still records
mandatory-overflow and token-unavailable fault-injection evidence as
incomplete. The operational report's stored implementation SHA predates the
provider-label-only follow-up; no ranking code changed, but exact evidence
should be regenerated if the package is later reconsidered.

### Re-review verdict

**RETHINK**

The runtime safety and fallback defects are fixed, but the frozen W-06B quality
gate remains far from its minimum precision target and fails TEST precision and
MRR non-regression. The lexical reranking design should be reconsidered under
a new bounded contract or amended evidence plan before further tuning. W-06B
is not SHIP; retrieval/context scores must not increase, V2 remains SHADOW,
and Phase 20 remains FROZEN / LOCKED.
