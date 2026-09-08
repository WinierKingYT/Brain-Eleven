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
