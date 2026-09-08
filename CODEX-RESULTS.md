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
