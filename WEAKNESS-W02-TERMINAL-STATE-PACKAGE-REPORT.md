# W-02 Terminal-State Closure — Package Report

**VERDICT: REVIEW PENDING / NOT ACCEPTED**
**Implementation revision:** `c842320ae091e6fadad76536baa08a2aac69cb2b`
**Test and validation revision:** `93436fbf232d21f5ebc584fb642689f0061cf657`
**Defect baseline:** `b9d4c06` (the intervening `8b0e382` changes only the
contract review document)
**Phase 20:** FROZEN / LOCKED
**V2 runtime:** SHADOW

## Bounded change

Only `scripts/capture_queue.py`, the new
`tests/test_w02_terminal_state.py`, and this package report change. Existing
queue and IG-02 tests remain unchanged. Implementation and tests were committed
and pushed separately.

`commit()` now atomically writes and fsyncs the `COMMITTED` document, including
`committed_at`, in its processing location before renaming it into `completed`.
Recovery closes an already-committed processing document immediately, without
waiting for a lease. It also reconciles valid legacy `CLAIMED`/`PROCESSING`
documents in `completed` under the existing queue lock. The completed location
is the evidence that the old commit rename occurred; repair does not call a
worker, extractor, MemoryStore or StateStore. For a legacy record without a
commit timestamp, `committed_at` records reconciliation time.

Recovery reads existing terminal ledger IDs once per locked pass and appends
the existing content-free `COMMITTED` record only when absent. This closes a
crash after rename or document reconciliation but before bookkeeping. A crash
after the append does not cause another terminal record on recovery. Settled
documents and ledger entries are unchanged on repeated recovery.

Duplicate enqueue uses the same terminal reconciliation path and returns the
durable document status. It preserves the original idempotency key and also
reports `PROCESSING` accurately for a currently processing document. Filename,
job and event identity mismatches, unsupported terminal states, invalid commit
timestamps and unreadable completed documents fail visibly rather than being
promoted. Existing public statuses, queue lock, worker effect ordering,
retry limits, leases, content retention and canonical authority stay intact.

## Before / after evidence

The baseline queue module was loaded directly from `git show
b9d4c06:scripts/capture_queue.py` into an isolated process with a temporary
vault. An injected process exit at the first completed-folder rewrite produced:

| Metric | Baseline | Current focused evidence |
| --- | --- | --- |
| Post-rename document | `completed/PROCESSING` | `completed/COMMITTED` |
| Recovery of that baseline state | 0 repairs; remains inconsistent | 1 repair; terminal state and ledger closed |
| Duplicate receipt vs. document | `COMMITTED` vs. `PROCESSING` | Both `COMMITTED` after reconciliation |
| Stranded terminal documents after recovery | 1 in baseline reproduction | 0 in tested cases |
| Canonical effects per worker crash/recovery case | Existing worker receipt boundary | Exactly 1 effect and 1 operation receipt in all 5 cases |
| Capture receipt files per worker case | Existing receipt boundary | Exactly 1 |
| Extra terminal ledger entries on repeated repair | No baseline repair | 0 |
| New focused successor coverage | 0 | 33 cases |

The worker tests preserve the full MemoryStore and StateStore snapshots after
recovery and fail if extraction runs again. The pre-terminal-write case uses
the existing lease retry and verified effect receipt; that existing replay
refreshes the receipt observation timestamp while preserving its identity and
effect fields. Terminal repair cases leave the receipt unchanged.

## Fault-injection matrix

The new test module covers:

- Commit exits before terminal rewrite, after rewrite/before rename, after
  rename/before ledger, and after ledger append.
- Both legacy completed statuses and stranded `COMMITTED`, repaired through
  recovery and duplicate enqueue.
- Recovery exits before rewrite, after rewrite, and after terminal ledger
  append, followed by repeated recovery with no additional writes or events.
- Completed JSON corruption, filename/document identity mismatch, job/event
  idempotency mismatches, illegal completed state, malformed timestamp and
  missing claim timestamp, through recovery and duplicate lookup.
- Five worker scenarios covering all four commit boundaries plus the legacy
  completed state. Each retains one canonical effect, operation receipt and
  capture receipt, and reaches one completed queue record.
- Completed status/location agreement, attempt preservation, duplicate receipt
  accuracy and terminal ledger exclusion of session IDs and private paths.

Faults use a `BaseException` process-exit sentinel so worker `Exception` retry
handling cannot conceal the interrupted transition. All vaults are temporary;
production canonical stores and standing untracked artifacts are untouched.

## Validation

Runtime: repository `.venv/Scripts/python.exe`. The system Python cannot load
the existing test conftest because it lacks `defusedxml`; no dependency changes
were needed when using the repository environment.

| Command | Result |
| --- | --- |
| `python -m pytest tests/test_capture_queue.py tests/test_ig02_capture_closure.py tests/test_w02_terminal_state.py -q` | **83 passed in 34.55s** |
| `.venv\\Scripts\\python.exe -m pytest tests -q` | **1157 passed, 2 warnings in 258.34s** |
| `python -m flake8 scripts brain_eleven tests authority context_compiler_v2 context_density_v2 context_router retrieval_decision_v2 evals conftest.py --select=E9,F63,F7,F82` | **PASS** |
| `python -m compileall -q scripts brain_eleven tests authority context_compiler_v2 context_density_v2 context_router retrieval_decision_v2 evals conftest.py` | **PASS** |
| `git diff --check` | **PASS** |

The combined focused run includes the existing 50 queue/IG-02 cases without
modification and 33 new cases. The report is a documentation-only follow-up to
the exact implementation/test revision above.

## Known limitations and review gate

- Terminal ledger lookup is linear in ledger size once per recovery pass;
  completed documents are scanned to detect legacy states and missing terminal
  bookkeeping. Retention and ledger indexing remain outside this package.
- A malformed or torn ledger JSON record raises `CAPTURE_QUEUE_CORRUPT`.
  Recovery does not silently discard corrupt ledger data or claim success.
- Fault injection proves interrupted process transitions using the existing
  atomic-write/file-fsync primitive. It does not simulate hardware power loss
  or introduce filesystem directory-fsync guarantees.
- Queue reconciliation relies on the existing worker receipt/effect ordering
  and the legacy completed location; it does not independently revalidate
  canonical effects or repair arbitrary external tampering.
- Transcript policy, late locator handling, prompt semantics, extraction,
  canonical schema, retention, V2 promotion and Phase 20 changes remain outside
  scope.

Independent read-only implementation review must return `SHIP`, `FIX-FIRST`
or `RETHINK` against the recorded revision and evidence. The implementation
agent does not grant acceptance. **Current verdict: REVIEW PENDING.**
