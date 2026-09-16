# W-25 HTTP Scope and Authorization — Package Report

**PACKAGE:** W-25 HTTP project-scope/authorization  
**REVISION:** `65510c32d246ed2dc047e27c071294d8f5d85f3f` (code/test head)  
**OBJECTIVE:** Close the unauthenticated `retrieval_scope=all` and direct
memory-ID scope leaks at the HTTP boundary while preserving canonical stores,
registry authority, lifecycle writes, retrieval behavior, and Phase 20 freeze.

## FILES CHANGED

- `scripts/search-api.py`
- `tests/test_search_api.py`
- `tests/test_w08d_search_api_lifecycle.py`
- `tests/test_w13_project_root_id_scope.py`
- `tests/test_w25_http_scope.py`

No MemoryStore, ProjectRegistry, scope-filter, graph, retrieval, V2, or
Phase 20 implementation was changed.

## ROOT CAUSES ADDRESSED

- Scope-bearing HTTP routes now pass through one normalized authorization
  decision.
- `all` is restricted to a configured `BRAIN_ELEVEN_API_KEY`; an untrusted
  query/header cannot grant it.
- Project contexts are syntax-checked and validated against the active,
  proactively enabled ProjectRegistry record before corpus access.
- Direct memory-ID reads use the same filtered context and return a
  content-free not-found result for foreign or missing project context.
- Anomaly responses use the authorized filtered corpus; the legacy whole-vault
  anomaly chat path is content-free for ordinary scoped requests.
- Non-loopback deployments fail closed without the configured admin key, while
  the exact loopback allowlist remains usable for ordinary scoped reads.
- Operational and derived-state routes are covered by the middleware policy.

## TESTS ADDED

`tests/test_w25_http_scope.py` covers two-project isolation, default/global and
project scopes, admin `all`, direct-ID protection, registry failures, anomaly
filtering, non-loopback/key policy, malformed inputs, protected operational
routes, and read-only denial effects.

## TESTS EXECUTED

- Focused HTTP/scope suite: **100 passed, 2 warnings**
- Full regression: **1435 passed, 4 skipped, 2 warnings**
- Critical flake8 (`E9,F63,F7,F82`) on every changed Python file: **PASS**
- `compileall` on changed Python files: **PASS**
- `git diff --check`: **PASS**

All commands were run against the exact revision recorded above using the
repository `.venv` interpreter.

## QUALITY METRICS BEFORE / AFTER

The read-only audit reproduced cross-project results for unauthenticated
`/search?retrieval_scope=all` and `/memories?retrieval_scope=all`, and returned a
foreign project record from `GET /memories/{id}` without project context.

The focused two-project matrix now records no unauthorized cross-project
records, no unscoped foreign direct-ID result, and deterministic bounded policy
errors. The implementation does not claim to improve retrieval relevance or
PRE-13 holdout quality.

## SAFETY METRICS

- wrong-project leakage in the focused matrix: **0**
- unauthorized `all` access: **0**
- forbidden/non-loopback protected access without key: **0 allowed**
- denied-read canonical revision/backup/graph/cache mutation: **0**
- policy error content/path/secret echo: **0 observed**

## KNOWN LIMITATIONS

The API key is a bearer credential for the trusted internal/admin surface; W-25
is not a multi-user identity or tenant-authentication system. Existing legacy
success/error response behavior outside the new scope-policy codes remains out
of scope. PRE-13 retrieval-quality failures and native-client trust/latency
acceptance remain separate packages.

## OPEN FAILURES

No bounded W-25 implementation failure is known from local evidence. The
independent read-only review and its exact verdict are still pending.

## INDEPENDENT REVIEW

**PENDING** — self-review is not acceptance.

## SCORE BEFORE / AFTER

Scope/fail-closed safety was approximately **8.9/10** before this package.
The bounded after-score is **provisional 9.1/10 pending independent review**;
other intelligence dimensions are unchanged.

## VERDICT

**REVIEW PENDING — do not self-SHIP.**
