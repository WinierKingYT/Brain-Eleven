# Codex task results

## T1 — `scripts/search-api.py`

- Decision: cover it. The API is live because `Dockerfile` launches it as the
  container command; `docker-compose.yml` builds that image. No runtime-service
  import was found, and `post_session_maintenance.py` only mentions the API in
  documentation text.
- Changed: bounded `/search` queries to 1–4096 characters; added tests for
  malformed and oversized queries, project-scope isolation across search/list/
  rank, empty-corpus behavior, and existing fail-closed cache/graph/chat
  branches. Focused coverage is 81% (up from 79%).
- Tests: 722 passed before; 729 passed after; both runs emitted the existing 2
  deprecation warnings.
- Finding: API-key authentication exists and is covered, but this module has no
  rate-limiting middleware or 429 branch. Rate limiting was deliberately left
  out of T1 rather than invented here.
- Out of scope: T2 and T3 were not started.

## T2 — SessionStart hook: make failure observable

- Changed: `brain-eleven-session-start` now atomically writes
  `.claude/session-run-result.json` on every invocation with timestamp, compiler
  exit status, branch, duration, and truncated compiler errors. Bootstrap
  failures that recover through `--stdout` are retained in separate breadcrumb
  fields; the hook itself still exits 0.
- Changed: `brain_eleven doctor` reports `last SessionStart: ok/failed at <ts>`
  and returns a non-zero CLI status when the breadcrumb records a compiler
  failure. Added success, failure, and doctor health tests.
- Decision: kept the existing `.claude/session-run-result.json` artifact path
  and treated a successful `--stdout` fallback as healthy while preserving the
  failed bootstrap status for diagnosis.
- Tests: 729 passed before; 732 passed after; both runs emitted the existing 2
  deprecation warnings.
- Out of scope: T3 was not started.

## T3 — remove the hyphen/underscore duplicate modules

- Audit: `scripts/project-registry.py` ↔ `scripts/project_registry.py` was the
  only exact `-`/`_` twin in the full `git ls-files scripts/` set. The other
  hyphenated Python files — `context-compiler.py`, `dedupe-validated-memory.py`,
  `demo-phase7-complete.py`, `embedding-generator.py`, `hybrid-search.py`,
  `install-cross-project-memory.py`, `memory-compiler.py`, `memory-lifecycle.py`,
  `memory-retriever.py`, `memory-validator.py`, `migrate-legacy-memory.py`,
  `migrate-memory-scope.py`, `ml-ranker.py`, `prompt-counter.py`, `search-api.py`,
  and `semantic-search.py` — have no same-name underscore counterpart; no
  underscore file had a missing hyphen twin.
- Changed: moved the hyphenated registry CLI `main()` into
  `scripts/project_registry.py` and removed `scripts/project-registry.py`.
  The canonical `ProjectRegistry` implementation and the
  `brain_eleven.projects.registry` bridge were not changed.
- Callers updated: `tests/test_remember.py` now loads `project_registry.py`;
  `tests/test_pre12_project_caller_migration.py` no longer inventories the
  deleted wrapper. No hook, Dockerfile, Makefile, docker-compose, or runtime
  caller referenced this exact wrapper; history documentation was left stale
  only where applicable.
- Decision: runtime loading remains on the underscore implementation through
  the existing package bridge; distinct hyphenated legacy entry points were
  deliberately left in place because they are not separator twins.
- Test artifact: regenerated `evals/reports/baseline-v3.json` so its
  deterministic source fingerprint includes the consolidated canonical module.
- Tests: 732 passed before; 732 passed after; both runs emitted the existing 2
  deprecation warnings. The first post-change run found the expected stale
  baseline fingerprint (`731 passed, 1 failed`), which was regenerated before
  the final green run.
- Out of scope: the remaining standalone CLI/hook bootstraps listed in T4
  below, and all non-twin hyphenated modules.

## T4 — stop runtime code from mutating `sys.path`

- Changed: added `scripts*` to the setuptools package discovery configuration;
  `scripts.memory_store` and `brain_eleven.memory.store` now resolve through
  the editable package boundary. Replaced the eager legacy imports in
  `scripts/__init__.py` with a lazy compatibility loader.
- Changed: removed per-test path mutation and the old `tests/conftest.py`.
  The single root `conftest.py` provides bare-name compatibility aliases via
  `sys.modules` only; it does not modify `sys.path`.
- Changed: removed runtime path mutation from the library modules, package
  re-export shims, evaluation adapters, and first-party runtime imports. The
  canonical MemoryStore, StateStore, and ProjectRegistry implementations and
  their semantics were not moved or changed.
- Decision: preserved the copied-hook `try/except ModuleNotFoundError`
  fallbacks in `scripts/memory_store.py`, `scripts/state_store.py`,
  `scripts/project_registry.py`, `scripts/capture_event.py`, and
  `scripts/capture_queue.py`. The native launcher keeps one direct-file CLI
  bootstrap because installed hooks invoke `brain_eleven/runtime/launcher.py`
  by absolute path.
- Remaining path bootstraps (all are direct standalone CLI or hook entry
  points; no test/library path hacks remain):
  `brain_eleven/runtime/launcher.py` (native direct-file hook),
  `scripts/context-compiler.py` (SessionStart copied hook),
  `scripts/dedupe-validated-memory.py` (maintenance CLI),
  `scripts/hybrid-search.py` (legacy search CLI),
  `scripts/memory_backup.py` (backup CLI),
  `scripts/memory-lifecycle.py` (lifecycle CLI),
  `scripts/memory-retriever.py` (legacy retrieval CLI),
  `scripts/memory-validator.py` (copied validation CLI),
  `scripts/migrate-legacy-memory.py` (migration CLI),
  `scripts/migrate-memory-scope.py` (migration CLI),
  `scripts/post_session_maintenance.py` (SessionEnd copied hook; two
  bootstraps),
  `scripts/remember.py` (manual-capture command; two bootstraps),
  `scripts/search-api.py` (Docker/API server; two bootstraps),
  `scripts/semantic-search.py` (legacy semantic-search CLI), and
  `scripts/state.py` (typed state CLI).
- Verification: from an arbitrary CWD, the provisioned interpreter imported
  `scripts.memory_store` and `brain_eleven.memory.store` with identical
  `MemoryStore` identity and no new `sys.path` entries. `pip install -e .`
  was attempted with `--no-deps --no-build-isolation`; the supplied venv has
  no `setuptools` build backend and no cached wheel, so pip could not execute
  the standard setuptools backend without network or adding a dependency.
- Baselines: regenerated mutable `baseline-v3` after the fingerprinted source
  changes; immutable `baseline-v2` write was rejected by its own guard and its
  historical manifest check passes.
- Tests: 732 passed before; 732 passed after; both full-suite runs emitted the
  existing 2 deprecation warnings. Tracked Python files containing the path
  mutation decreased from 96 to 15 (repo-wide tracked files: 98 to 15).
- Out of scope: T5 and all remaining standalone CLI/hook bootstraps listed
  above.
