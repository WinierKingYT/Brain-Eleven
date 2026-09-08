# PRE-13 runtime integration and Phase 20 closure

Updated: 2026-09-07. Authority: **HISTORICAL DEVELOPMENT CHECKPOINT**.

This record preserves PRE-13 work and evidence at `7e6f55a82465f6fef7abf8318a451308bbe9a0e9`; it does not describe later IG-00 changes as verified. The Intelligence Graduation program supersedes this package's scheduling and former “freeze blocked” terminology. **Phase 20 is FROZEN as a feature decision, not graduated.** Quality failure, current-code CI and real-use limitations remain separate. Read PROJECT-STATUS.md and RUNTIME-DATAFLOW.md for current state.

The following workstream status and operating details describe the checkpoint. They do not open Phase 20, accept IG-00, or authorize runtime promotion.

## Five closure workstreams

| Workstream | Implementation and remaining evidence |
|---|---|
| Context quality | Production and offline evaluation now use the same Task → Router → Authority → Retrieval Decision → Density → Compiler chain. Individual critical needs, real diversity selection, token costs, selection order, stale revisions and final scope checks are implemented. Frozen corpus-v2 precision/recall and V1 nonregression gates still fail. **OPEN**. |
| Claude / Codex adapters | Native SessionStart, UserPromptSubmit, Stop and SessionEnd adapters; incremental transcript parsing; bounded inputs; warning-and-continue; delivery deduplication; Windows windowless execution. Automated native subprocess tests pass. Installed-client hook trust and actual daily-use observations remain separately unverified. |
| Durability / operations | Atomic memory/state operation receipts; resumable schema migration; additive hook installation with interrupted-upgrade recovery; review acceptance/rejection/expiry; singleton worker/service; lease recovery; backup/restore preserving receipts. The final synthetic 1,000-record process performance measurement passed. |
| Validation | Windows tests, runtime coverage, critical lint and runtime security checks passed (details below). The new Windows/Linux runtime workflow is implemented but has no current-revision remote CI result yet. No independent final review has been completed. **OPEN**. |
| Freeze / handoff | This document and the operating instructions record the actual evidence. The former technical closure remains unaccepted. IG now freezes features independently; quality, regression, cross-platform CI and review are tracked as separate gates. A local checkpoint is not graduation. **OPEN**. |

## Quality evidence and corpus limitation

The legacy fixture, labels, split boundaries and acceptance thresholds remain
unchanged: precision ≥ 70%, required recall ≥ 80%, no forbidden/project/lifecycle
leaks, and no precision/recall regression against budgeted V1.

The 30-case corpus-v2 holdout with 1,000 added irrelevant records measured
runtime precision 4.52%, required recall 14.71%, and zero forbidden/project/
lifecycle leaks; V1 measured 12.67% and 50% respectively. Context p95 was
92.38 ms. These are failing quality results despite passing latency and safety
measurements (final rerun: 99.05 ms). See local `.phase-evidence/pre13-holdout-1000.json` for the
implementation fingerprint and per-case results; local evidence is ignored by Git.

Inspection of `evals/corpus_builder.py` and `evals/corpus_v2_builder.py` found
questions that differ only by a scenario number while required IDs rotate
through unrelated rules. The requested fact is not specified in those
questions. This prevents interpreting all legacy labels as answerable relevance
tests. It does not justify silently changing labels, thresholds, or holdout
results. The IG program authorizes a separate evaluation foundation in IG-01 after IG-00 acceptance. Corpus design and labels must be contracted and frozen before tuning. Existing failure evidence is
retained either way. No task IDs or expected labels are fed to retrieval.

## Latest local verification

Windows / Python 3.13.7, 2026-09-07:

| Check | Result |
|---|---|
| Full unit suite | 650 passed, 41 integration/graduation deselected; 67.19 seconds. |
| Additional native shell contract | 1 passed after the full suite; installed Codex PowerShell command preserves JSON stdin/stdout through `pythonw.exe`. |
| Integration / graduation suite | 41 passed, zero skipped; 13.16 seconds. These are automated Foundation tests, not real-use graduation. |
| Runtime line coverage | 82.12%, threshold 80%. |
| Critical lint / runtime Bandit medium+ | Zero findings. |
| Historical baseline-v1/v2 and current baseline-v3 | All checks passed. |
| 1,000-record process benchmark | 40 Stop hooks + 40 prompt hooks; p95 297.78 ms / 417.02 ms. |
| Queue delay | p95 1,988.33 ms; maximum 2,077.54 ms; all 40 jobs completed, zero dead letters. |
| Service startup / singleton | Cold start 1,072.64 ms; repeated startup retained the same service identity. |
| Frozen quality holdout | **FAIL**; gates and corpus unchanged. |

Quality and final performance reports share implementation fingerprint
`4c4bf55112660e5fe95e47250793f88a32a09cefb2e5760a4b141377978ec56e`.
One earlier test run during a concurrent performance benchmark encountered a
local connection timeout. Serial hidden-process verification passed; the
performance figures above come from the subsequent serial run. Two existing
FastAPI/Starlette deprecation warnings remain. This does not establish remote
Linux CI, native-client trust, an independent review, or actual live use.

## Local operation

Run commands from the repository using the Python environment containing
`requirements.txt`:

```powershell
python -m brain_eleven install
python -m brain_eleven doctor
python -m brain_eleven status
python -m brain_eleven review --no-open
python -m brain_eleven context "Which database did we choose?" --project-root .
python -m brain_eleven worker --once
```

Installation is additive and enables SHADOW for the opted-in vault project.
Other client settings and unrelated hooks are preserved. Native client trust
must be checked in the client; `doctor` reporting configured hooks does not
prove client trust or actual hook execution. A changed hook command may require
native client review. The installer never approves trust automatically.

Windows hooks use the environment's `pythonw.exe` and preserve JSON stdin/stdout
pipes. Service and verification subprocesses suppress console windows. For
agent-driven PowerShell checks, launch Python with `Start-Process -WindowStyle
Hidden` and redirect stdout/stderr to local evidence files. Do not run visible
terminal helpers or open the browser unless needed by the user.

The review UI is loopback-only and requires the local token for API access.
The `review --no-open` command prints a private URL without opening a tab; do
not commit/share its fragment token. Runtime configuration, queues, evidence,
review candidates, delivery observations and tokens are local ignored files.
Raw transcripts are read incrementally from native client files and are not
copied into runtime storage. Safe pending proposal text is retained for up to
seven days of operational expiry; an offline machine cannot perform physical
deletion until the worker or review API next runs. Acceptance, rejection and
expiry remove proposal text. The optional local model is disabled by default,
accepts only literal loopback HTTP endpoints, and can propose review items only.

The local service starts on demand and exits after 15 minutes without activity.
A stopped/crashed service can restart on the next hook; a 10-second start
throttle prevents repeated spawning. Capture remains durable in the queue;
expired processing leases are recovered by the next worker. Hook failure warns
and allows the user's work to continue.

## Stop, uninstall and rollback

```powershell
python -m brain_eleven rollout OFF
python -m brain_eleven uninstall
python -m brain_eleven migration rollback
```

Uninstall stops the runtime, removes only journaled native hook entries and
preserves canonical data. It restores availability of the pre-existing legacy
hooks by removing the native-install marker. Migration rollback is allowed only
while OFF and only when neither canonical store has changed since migration;
it refuses to discard operation receipts or subsequent work. If data changed,
use a reviewed backup/restore into an empty vault instead. Keep migration
backups until normal operation has been verified.

## Reproducible checks

```powershell
python -m pytest tests/ -q -m "not integration and not graduation"
python -m pytest tests/ -q -m "integration or graduation"
python -m pytest tests/test_pre13_runtime.py -q --cov=brain_eleven/runtime --cov-fail-under=80
python -m evals.runtime_eval --suite holdout --noise-count 1000 --report .phase-evidence/pre13-holdout-1000.json
python -m evals.runtime_benchmark --report .phase-evidence/pre13-process-performance.json
python -m evals.baseline_snapshot --baseline baseline-v1 --check
python -m evals.baseline_snapshot --baseline baseline-v2 --check
python -m evals.baseline_snapshot --baseline baseline-v3 --check
python -m bandit -r brain_eleven/runtime -q -ll
```

Baseline-v1/v2 remain immutable historical reports. Baseline-v3 checks current
compatibility inputs. A quality FAIL exits nonzero and blocks CANARY promotion;
CI does not suppress that failure. Synthetic fixtures may exercise CANARY in
temporary vaults; they do not promote the real vault or count as real use.

## Separately pending real-use graduation

Technical closure cannot replace actual observations: at least 20 real turns,
five sessions, 40 independently human-labeled tasks, both native clients,
capture precision ≥ 98%, quality/nonregression/safety gates, hook p95 ≤ 500 ms,
context p95 ≤ 2 seconds, and no dead letters remain required. Local human
labels must reference actual emitted delivery IDs and capture operation IDs.
An EMITTED receipt records stdout delivery, not proof that a client/model used
it. Human confirmation remains necessary. ACTIVE recomputes gates and rejects
a hand-written PASS flag. No real-use graduation is claimed here.
