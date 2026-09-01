# Brain-Eleven v3 — Current Project Status

**Last updated:** 2026-09-01
**Current milestone:** Phase 13 cross-project memory and Phase 14 runtime hardening complete locally

## Product boundary

Brain-Eleven is a local, privacy-first second-brain system. Canonical memory
remains in the vault; the API, hooks, context compiler, knowledge graph and
search layers consume that same validated store rather than creating parallel
write paths.

## Verified current state

| Area | Status | Evidence |
|---|---|---|
| Canonical memory schema | ✅ | Scope v2 migration applied to the real vault: 46 memories, canonical revision 1, recoverable pre-migration backup. |
| Project isolation | ✅ | Project memories deduplicate and detect conflicts only within their project; global memory remains explicitly shareable. |
| Retrieval and context | ✅ | Current-project memories rank first, global memories remain eligible, and other-project memories are excluded unless explicitly requested. |
| Knowledge graph provenance | ✅ | Memory nodes retain project provenance through `BELONGS_TO` project relations. |
| Concurrent writes | ✅ | Canonical writes lock, reload and atomically replace the latest store to prevent lost updates. |
| Global `/remember` installation | ✅ | Idempotent installer upgrades known legacy artifacts, preserves unrelated Claude settings and backs up managed changes. |
| Hook portability | ✅ | Global and local hooks resolve Windows/WSL paths and `python3`/`python` safely; unopted projects fail closed. Corrected 2026-09-01: the installed `SessionStart`/`SessionEnd` commands only offered the WSL `/mnt/c/...` form, which a native Windows + Git Bash host (the actual target machine) cannot resolve at all - confirmed by executing the exact installed command directly and getting `No such file or directory`, contradicting the smoke-test claim below. `_shell_hook_command()` now emits `bash <Git-Bash-native form> || bash <WSL form>`, re-installed, and re-verified by executing the corrected command directly (real bootstrap output, exit 0). |
| Prompt checkpoints | ✅ | The local prompt counter writes atomic state and every-15-prompt checkpoint without interrupting the prompt flow. |
| API regression suite | ✅ | Unit and API-integration tests are split; integration tests use the actual FastAPI lifecycle. |
| Container configuration | ✅ | Compose validation passes; service ports bind to loopback on the host and health checks use only Python standard-library dependencies. |

## Local verification evidence

| Check | Result |
|---|---|
| Full automated suite | **311 passed** |
| Coverage gate | **85%** (minimum: 80%) |
| Unit suite | **272 passed** |
| FastAPI integration suite | **38 passed** |
| Compose configuration | `docker compose config --quiet` passed |
| Real global hook smoke test | Originally claimed passing, but this was not verified against the actual target host - see the corrected Hook portability row above. Re-verified 2026-09-01 on the real machine after the fix: the exact command string in `~/.claude/settings.json` was executed directly, producing real bootstrap output (exit 0) for SessionStart, and a silent, non-crashing exit 0 for SessionEnd run from an unopted project directory. |
| Real canonical migration | 46 records migrated, no records marked for review, exact backup created |

## Remaining operational validation

1. Docker Desktop's Linux daemon was unavailable on this workstation, so a live
   `docker compose up` healthcheck remains an environment-level validation step.
2. A public deployment, backup/restore drill and sustained daily-use telemetry
   are separate operational work; none is required for the local-first core.
3. The pending commit still needs remote GitHub Actions confirmation after it is
   pushed.

## Operational guidance

- Keep project capture opt-in. Proactive capture may be enabled only after the
  project is registered and its scope policy is understood.
- Use project-scoped memory for project decisions. Use global memory only for
  facts and practices intentionally shared across projects.
- Retain `.claude/validated-memory.json.pre-scope-v2-*.bak` until the migrated
  store has been observed in normal use.
- Treat a hook warning as a degraded convenience feature, never as permission to
  bypass the validator or write directly to canonical memory.

## Historical planning documents

Phase plans preserve the original design and execution record. Current status
is maintained here; the Phase 13 plan is marked as historical so old runtime
assumptions are not mistaken for the verified system state.
