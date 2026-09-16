# W-25 HTTP Project-Scope and Authorization Contract

**Status:** CONTRACT REVIEW PENDING — implementation is not authorized by this document  
**Finding:** the HTTP API exposes the whole memory corpus when an unauthenticated
request selects `retrieval_scope=all`, and the direct memory-ID route does not
apply any project-scope check.  The current API-key middleware is optional, so
the documented loopback assumption is not enforced at the HTTP boundary.  
**Priority:** P1 project-isolation and authorization safety  
**Audit baseline:** `7a7ac22c6a063da190a6309e16e6f8f64dd577f0`  
**Phase 20:** FROZEN / LOCKED  
**V2:** SHADOW

## Bounded objective

Close the observed HTTP read-boundary gap while preserving the canonical
MemoryStore, ProjectRegistry, existing lifecycle/CAS writes, retrieval
algorithms, and trusted in-process APIs.  A request must receive only the
scope it is authorized to request.  The HTTP layer is the only implementation
surface in this package: `scripts/search-api.py` and focused API tests may
change; `scripts/memory_scope.py`, MemoryStore, ProjectRegistry, search/rank
weights, graph projection, compiler, V2 rollout and Phase 20 are outside the
package.

This package does not claim to authenticate a human identity.  It defines a
small, explicit boundary for this local API:

* an ordinary request may use the default/global scope or one explicitly
  validated project context;
* a cross-project `all` view is an administrative/internal operation and
  requires the configured `BRAIN_ELEVEN_API_KEY`;
* when the server is configured for a non-loopback host, starting or serving
  sensitive routes without that key must fail closed;
* a valid key is a bearer credential for the already trusted internal/admin
  surface.  It is not copied into memory records, telemetry or error bodies.

No request parameter may silently widen a project-scoped request to `all`.

## Evidence and current mechanics

The following references are from the exact audit baseline above.

### Request and server context

1. `scripts/search-api.py:122-133` accepts `project_id` and the four
   retrieval scopes (`default`, `global`, `project`, `all`) for `/search` and
   `/rank`.
2. `scripts/search-api.py:145-150` chooses one process-wide `vault_path` from
   `VAULT_PATH` or the user's default Brain-Eleven directory.  There is no
   per-request trusted project identity in this module today.
3. `scripts/search-api.py:300-313` applies the API-key middleware only when
   `BRAIN_ELEVEN_API_KEY` is set.  With no key, every non-public route passes;
   the public paths are `/health`, `/docs`, `/redoc` and `/openapi.json`.
4. `scripts/search-api.py:1154-1175` warns that a missing key is acceptable
   for loopback use and lets `BRAIN_ELEVEN_HOST` choose a non-loopback bind,
   but does not reject that unsafe combination.
5. `scripts/memory_scope.py:230-258` is the existing scope filter.  It
   requires a project ID for `project`, permits `all` without one, and the
   `all` branch returns every record.  This helper remains unchanged; W-25
   wraps it with an HTTP authorization decision.

### Routes that currently consume the untrusted scope selector

* `/search` (`scripts/search-api.py:354-403`) passes request fields directly
  to `filter_memories` at `:371-375`, then to the hybrid engine at `:387-392`.
* `/rank` (`:412-445`) filters both the stored corpus (`:424-428`) and the
  caller-supplied candidate set (`:433-438`).
* `GET /memories` (`:494-524`) accepts `project_id` and `retrieval_scope` and
  filters at `:509-513`.
* `GET /memories/{memory_id}` (`:608-625`) scans the entire raw list at
  `:616-620` and currently has no scope or project parameter.
* `GET /digest` (`:955-979`) passes both selectors to `MemorySummarizer` at
  `:969-975`.
* `GET /anomalies` (`:981-993`) currently has no selector and calls
  `AnomalyDetector.detect_all()` over the whole vault.  The detector emits
  short content excerpts (`brain_eleven/support/anomaly.py:86-89,
  :110-116, :130-133, :150-153, :190-193, :203-207`), so this is a
  content-bearing scope route and must be brought under the same policy.
* `GET /graph/entities` (`:1006-1024`), entity relationships (`:1026-1047`)
  and traversal (`:1049-1067`) pass the selectors to the canonical graph
  projection.  `all` is therefore a graph exposure as well as a memory
  exposure.
* `POST /chat` (`:1086-1108`) passes the selectors to `ChatAgent` at
  `:1102-1108`.

The complete current route policy must be recorded before implementation.  At
minimum it is:

| Method/path | Boundary class | W-25 requirement |
|---|---|---|
| `GET /health`, `/docs`, `/redoc`, `/openapi.json` | public liveness/docs | no memory content; remain public |
| `GET /status`, `/metrics`, `/cache/stats` | aggregate/operational read | no new memory content; non-loopback key policy still applies |
| `POST /search`, `POST /rank`, `GET /memories`, `GET /memories/{id}`, `GET /digest`, `GET /anomalies`, `GET /graph/entities`, graph relationships/traverse, `POST /chat` | content-bearing scoped read | one helper; `all` admin-only; project context validated |
| `POST /memories`, `PUT /memories/{id}`, `DELETE /memories/{id}` | canonical mutation | preserve existing validation, scope, transaction/CAS and key policy; reject unauthorized project context before mutation |
| `POST /embed` (`:452-488`) | query/content processing | no memory corpus disclosure; include in non-loopback/key matrix |
| `POST /cache/clear` (`:942-949`), `POST /graph/rebuild` (`:1069-1084`) | derived-state mutation | admin/key or explicit local policy; no unauthenticated non-loopback access |

`/anomalies` is intentionally included as a scoped route: the implementation
may add `project_id`/`retrieval_scope` and pass a filtered list to
`AnomalyDetector.detect_all(memories=...)`, or choose a content-free/redacted
response, but it must not remain an unscoped whole-vault exception.  Existing
CRUD writes (`POST /memories`, `PUT /memories/{id}`, `DELETE /memories/{id}`)
already use the validation and scope helpers at `:529-597` and `:671-708`;
their canonical transaction and project checks remain intact while the same
request authorization policy is applied where a request names a project.

### Reproduced failure

The read-only audit used an isolated temporary vault containing distinct
project-A and project-B records and a TestClient import of the real app.  It
observed:

| Request | Current result | Safety implication |
|---|---|---|
| `POST /search` with `retrieval_scope=all` | records from both projects | unauthenticated corpus widening |
| `GET /memories?retrieval_scope=all` | records from both projects | unauthenticated corpus listing |
| `GET /memories/<project-b-id>` with no project context | HTTP 200 and full record | direct-ID scope bypass |
| `POST /search` with project-A + `project` | project-A result only | existing structural filter is retained |

The probe emitted only statuses, IDs/counts and bounded reason codes in its
notes; raw private memory content is not part of W-25 evidence.

Existing `tests/test_search_api.py:138-196` covers project-A filtering for
`/search`, `/memories` and `/rank`, but it does not exercise `all`, direct-ID
scope, project-registry authority or a two-project HTTP authorization matrix.
Its API-key tests at `:549-590` cover only missing/wrong/correct key behavior
for `/graph/stats`, not scope authorization.

## Required contract behavior

### 1. One HTTP authorization decision

Add a small private boundary helper or dependency in `scripts/search-api.py`.
All scope-bearing routes listed above must call it before reading a corpus,
graph, digest or chat result.  It must return a normalized request context or
a bounded error and must not mutate the canonical store.

The helper must distinguish:

* **default/global:** no project ID means global-only according to the
  existing `filter_memories` semantics; a project ID may select that one
  validated project plus global records.
* **project:** a non-empty project ID is mandatory, must be syntactically
  bounded, and must be validated against the existing ProjectRegistry read
  authority before content is loaded.  Unknown, corrupt, archived or
  disabled project records fail closed with a stable content-free code.  The
  helper must not auto-register, repair, reactivate or relabel a project.
* **all:** only a request carrying the configured API key may use this scope.
  A missing or wrong key returns a stable 403/401 policy error without a
  record, path, query or project label in the body.  If no key is configured,
  `all` remains unavailable; it must not silently become local-admin access.

The implementation may use a distinct internal/admin marker only if it is
derived from the already validated API-key middleware.  A caller-supplied
boolean, query parameter, project label or `X-` header cannot grant `all`.

### 2. Loopback and non-loopback startup policy

The existing local loopback default remains usable for ordinary scoped
requests.  The accepted loopback host values are exactly `127.0.0.1`, `::1`
and `localhost` (case-insensitive); `0.0.0.0`, `::`, an empty value with an
explicit non-loopback deployment, and every other value are treated as
non-loopback.  If `BRAIN_ELEVEN_HOST` is explicitly non-loopback, the
application must fail closed for sensitive routes unless
`BRAIN_ELEVEN_API_KEY` is set; the behavior must be deterministic and visible
at startup or on the first protected request.  `/health` and documentation
paths may remain reachable as public liveness surfaces.  Do not rely on a
warning alone.

This is a boundary check, not a redesign of deployment or Docker networking.
The package must document how tests select loopback/no-key versus authenticated
admin mode without leaking the user's environment.

### 3. Direct memory lookup uses the same policy

Extend `GET /memories/{memory_id}` with the smallest compatible project/scope
context needed to apply the helper (query parameters are acceptable).  Before
returning a record, filter it through the authorized scope:

* a global record may be returned only through default/global authorization;
* a project record requires the matching validated project ID;
* an ID from another project and an ID with no authorized context both return
  the existing content-free 404 shape (or an explicitly documented 403),
  never the record or a distinguishing private detail;
* an authenticated admin request may use `all` and retrieve the ID;
* deleted, superseded and resolved visibility must remain exactly as the
  existing read policy defines it; W-25 does not change lifecycle semantics.

The same helper must protect any new query parameters from becoming a second
authorization path.

### 4. Preserve writes and trusted internal callers

Do not alter MemoryStore, ProjectRegistry, `memory_scope.filter_memories`,
graph projection, ChatAgent, rank weights, embedding providers, V1/V2
selection or canonical write schemas.  Existing mutation checks
(`_validate_api_project_scope`, `MemoryStore.transact`, expected revisions and
graph rebuild behavior) must continue to work.  Direct Python callers that
already call `filter_memories` remain trusted in-process APIs; W-25 is the
HTTP boundary only.

### 5. Privacy and bounded errors

Authorization failures and the new W-25 boundary telemetry use stable
machine-readable codes such as `HTTP_SCOPE_REQUIRED`, `HTTP_SCOPE_FORBIDDEN`,
`HTTP_PROJECT_UNKNOWN` and `HTTP_ADMIN_KEY_REQUIRED` (the final names must be
fixed in the implementation and tests).  The no-echo rule applies to those
denial responses, their logs, and any new scope/auth telemetry: they must not
echo raw query text, memory content, API keys, vault paths, project labels from
an untrusted request or exception tracebacks.  Existing successful response
contracts (for example `/search`'s query echo and `/status`'s configured vault
path at `:339-345`) and unrelated legacy catch-all error text are pre-existing
out of scope for W-25; do not silently broaden this package into a general API
privacy rewrite.  A 404 for a foreign direct ID must not disclose whether
another project owns that ID.  Content-free telemetry may record route, scope
class, status code and a bounded reason.

### 6. No new broad capability

This package does not promote V2, tune retrieval, change context compilation,
add a graph reasoner, modify Phase 20, or introduce a second authority.  A
future authenticated multi-tenant design would require a separate contract;
W-25 closes the concrete unauthenticated `all` and direct-ID leaks only.

## Caller and test inventory

At the audit baseline, the production HTTP entry point is the single
`scripts/search-api.py` FastAPI app.  The repository callers are the route
handlers listed above; `tests/test_search_api.py` is the current end-to-end
caller (integration marker, TestClient fixtures at `:60-104`).  Additional
scope behavior is exercised by the existing `tests/test_phase14_scope.py`,
`tests/test_context_router.py`, `tests/test_authority_resolver.py` and
`tests/test_context_engine_operational_surfaces.py`, but those call package
surfaces directly rather than granting HTTP authorization.  The implementation
must re-run `rg` after edits and record any changed caller count in the package
report; comments, documentation and static inventory mentions do not count.

## Acceptance evidence and five gates

### Gate 1 — Boundary/identity proof

* Import the real FastAPI app in a clean interpreter and prove the new helper
  is used by every scope-bearing route.
* Prove that no request parameter or header other than the validated API-key
  path can grant `all`.
* Prove that `filter_memories` and canonical store identities are unchanged.

### Gate 2 — Adapter/route-only proof

* AST or equivalent structural check shows the diff is confined to the
  authorized HTTP boundary and tests; no duplicate MemoryStore,
  ProjectRegistry, scope filter, graph or retrieval implementation exists.
* Confirm no direct JSON/file write, new canonical authority or bypass of
  existing CAS/lock paths was introduced.

### Gate 3 — Parity and safety tests

Add focused tests with two registered projects and at least one global record:

* `/search`, `/rank`, `/memories` list, `/digest`, `/anomalies`, graph
  entity/relationship/traverse and `/chat` reject unauthenticated `all`
  (or reject an omitted/unknown project context) without returning either
  project's content; anomaly responses are either filtered to the authorized
  project or explicitly content-free/redacted;
* project-A context returns global plus project-A records and never project-B;
  missing/unknown/archived/disabled project context fails closed;
* direct GET of a project-B ID from project-A or without context is content-
  free 404/403; the matching project and authenticated admin behavior are
  explicit and tested;
* a configured API key permits the documented admin `all` route and still
  rejects missing/wrong keys; a non-loopback/no-key configuration fails closed;
* `/embed`, `/cache/clear` and `/graph/rebuild` follow the complete route
  matrix: no unauthenticated non-loopback access, and denied operations leave
  canonical revision, backup files, graph projection and cache bytes unchanged;
* existing CRUD create/update/delete, expected-revision conflict and graph
  rebuild tests remain green; no canonical revision changes on denied reads;
* malformed scope/project inputs produce bounded errors with no content/path/
  secret leakage.

The existing `tests/test_search_api.py` tests remain meaningful; update only
where the new required request context makes an assertion explicit.  Add a
separate focused file if that keeps the old behavior matrix readable.

### Gate 4 — Full verification

Run and record exact revision and results for:

* focused HTTP scope tests plus the existing `tests/test_search_api.py`;
* all scope/authority/context/graph/search regression tests;
* `pytest tests -q`;
* critical flake8 (`E9,F63,F7,F82`) on every changed Python file;
* `python -m compileall` on changed package/scripts;
* `git diff --check`.

Any pre-existing retrieval-quality or PRE-13 holdout failure remains visible;
it is not hidden by changing thresholds or skipping cases.

### Gate 5 — Independent read-only review

A reviewer who did not write the contract or implementation must inspect the
exact diff, route matrix, two-project probes, API-key/non-loopback evidence,
privacy errors, regression output and rollback/revert instructions.  The only
accepted verdicts are `SHIP`, `FIX-FIRST` or `RETHINK`; self-review cannot
close W-25.

## Rollback and operational safety

The package must document one bounded revert path: reverting the W-25 commit
restores the prior route behavior without a data migration.  No runtime
configuration may silently disable the new fail-closed policy in production.
Tests must prove that denied HTTP reads are read-only (canonical revision,
backup files, graph projection and cache bytes unchanged).  If a compatibility
switch is judged necessary, it must be explicit, authenticated, disabled by
default and covered by a separate security review; it cannot be an untrusted
query flag.

## Estimated change

Expected implementation size is approximately **80–180 production LOC** in
`scripts/search-api.py` plus **120–240 test LOC**, depending on whether the
route dependency is centralized.  No estimate authorizes widening the scope.

## Package report template

```text
PACKAGE: W-25 HTTP project-scope/authorization
REVISION: <exact code/test SHA>
OBJECTIVE: <bounded behavior closed>
FILES CHANGED: <production/tests/docs>
ROOT CAUSES ADDRESSED: <route and middleware evidence>
TESTS ADDED: <focused cases>
TESTS EXECUTED: <commands and exact results>
QUALITY METRICS BEFORE: <audit probe>
QUALITY METRICS AFTER: <scope/leakage/error metrics>
SAFETY METRICS: wrong-project=0, forbidden=0, content/path leakage=0
KNOWN LIMITATIONS: <explicit threat-model limits>
OPEN FAILURES: <none or exact P1/P2>
INDEPENDENT REVIEW: <review revision and SHIP/FIX-FIRST/RETHINK>
SCORE BEFORE: <scope/authorization score>
SCORE AFTER: <bounded score only>
VERDICT: REVIEW PENDING — implementation not yet authorized
```

**Plan status: REVIEW PENDING — implementation başlamadı.**
