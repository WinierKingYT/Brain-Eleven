# W-25 HTTP Scope Authorization Remediation — Independent Review

**Implementation under review:** `1f428d3fe6ce732183b3a77c09987173785951aa`
**Focused test remediation:** `39e3c7b87fc8aba588b8cad5b2ae9f5beaf454f7`
**Review/documentation head:** `9496b3eac39b29a3ad8ceb9b09687ddae4441cd3`
**Accepted contract:** `d7d4283aadaff9030053a16d7db3cc0cec3dfffc`
**Prior independent review:** `e6b3523aafca15a65b9856b4e67896e6045a0c4f` — `FIX-FIRST`
**Reviewer mode:** fresh, read-only re-review; no production code or standing untracked files changed
**Verdict:** **SHIP**

## Review scope and method

This review was performed against the exact requested current HEAD
`9496b3eac39b29a3ad8ceb9b09687ddae4441cd3`. I read the accepted W-25 contract,
the prior `FIX-FIRST` review, both remediation commits, the package report,
the HTTP boundary, the canonical graph projection, the entity extractor and
the chat graph/analyze handlers. Code discovery started with the indexed
codebase knowledge graph architecture and route/relationship queries, followed
by direct source and diff inspection because the graph index predates the
remediation symbols.

I ran the focused W-25 suite, the related HTTP/scope/authority/graph/search
regression set, and the full test suite. I also ran a fresh temporary-vault
two-project probe with distinct global, project-A and project-B technology and
phase mentions. The probe recorded only bounded IDs, statuses and response
shapes; it did not persist anything in the repository.

## Remediation assessment

The prior finding was that project-derived `TECHNOLOGY` and `PHASE` nodes had
no node-level project field and escaped the existing graph filter. The fix adds
`_HttpScopedGraphView` in `scripts/search-api.py:455-570`. For a non-admin
request it obtains the already authorized memory corpus through
`_load_http_memories`, collects its memory IDs, and admits a derived node only
when an incoming edge carries `source_memory` from that set. The pre-existing
graph visibility check still gates memory and `PROJECT` nodes. A valid
admin-key `all` request gets the explicit unrestricted view; an unprovenanced
derived node is suppressed.

`GET /graph/entities`, entity relationships and traversal construct this view
before returning graph data (`scripts/search-api.py:1331-1401`). Non-admin
`POST /chat` receives a shallow request-local copy whose graph field is the
same filtered view (`scripts/search-api.py:1426-1465`), so both graph-query and
analyze intents use the provenance filter while the canonical `ChatAgent` and
graph objects remain untouched. The underlying projection and extractor were
not changed by the remediation.

## Fresh two-project probe

The temporary vault contained active/proactive projects `a` and `b`, a global
Redis memory, an A memory mentioning Redis and Phase 7, and a B memory
mentioning PostgreSQL and Phase 9. Startup built the canonical projection;
read snapshots were taken after startup so startup rebuild output was not
mistaken for a read side effect.

| Request context | Returned graph IDs / result |
|---|---|
| default, no project | `g`, `tech_redis` |
| `retrieval_scope=global` | `g`, `tech_redis` |
| project `a`, default | `g`, `tech_redis`, `a`, `project_a`, `phase_7` |
| project `a`, global | `g`, `tech_redis` |
| project `a`, project scope | `tech_redis`, `a`, `project_a`, `phase_7` |
| project `b`, project scope | `b`, `project_b`, `tech_postgresql`, `phase_9` |
| admin `all` | all of the above, including `tech_postgresql` and `phase_9` |

The same probe verified the graph subroutes:

- `tech_redis` relationships in default/global returned only the global edge;
  project-A scope returned only the A edge.
- PostgreSQL relationships and traversal returned content-free `404` for
  project A and returned the B edge/subgraph for project B.
- Admin `all` returned the PostgreSQL relationship and its B memory, project
  and Phase 9 traversal nodes.
- Project-A graph chat for “what is connected to PostgreSQL?” returned no
  PostgreSQL name or ID; project-A “analyze PostgreSQL” likewise returned no
  foreign entity. Redis graph/analyze chat returned only global and A-derived
  names and connections.
- Unauthenticated `all` returned `403` with exactly
  `{"detail":{"code":"HTTP_ADMIN_KEY_REQUIRED"}}`.

The bytes of `validated-memory.json`, its backup, `knowledge-graph.json` and
its backup were identical before and after the non-admin graph/relationship/
traverse/chat reads. The probe reported `read_only_unchanged=true`.

## HTTP authorization and privacy gates

The shared `_authorize_http_scope` decision remains before corpus/graph loading
for all content-bearing routes, including direct memory lookup. It validates
project IDs through the read-only `ProjectRegistry`, requires an explicit
project for `project` scope, and grants `all` only from the middleware marker
set by a valid configured API key (`scripts/search-api.py:401-431`). The
middleware retains the exact loopback allowlist and fails closed for sensitive
non-loopback requests without the configured key (`scripts/search-api.py:594-613`).

The focused matrix covered default/global/project/all, direct foreign-ID
lookups, unknown/archived/disabled/corrupt registry states, malformed project
IDs, wrong/missing keys, untrusted admin parameters, public health, protected
operational and derived-state routes, and denied-read byte invariants. Denial
responses use fixed codes and did not echo project labels, query text, memory
content, paths or credentials in the exercised cases.

The remediation commits remain bounded: `1f428d3` changes only
`scripts/search-api.py`, and `39e3c7b` changes only
`tests/test_w25_http_scope.py`. No MemoryStore, ProjectRegistry,
`filter_memories`, graph projection, extractor, retrieval, compiler, V2 or
Phase 20 implementation changed.

## Validation evidence

- `.venv\\Scripts\\python.exe -m pytest tests/test_w25_http_scope.py -q` —
  **32 passed, 2 warnings**.
- `.venv\\Scripts\\python.exe -m pytest tests/test_search_api.py
  tests/test_phase11_graph_chat.py tests/test_graph_projection_revision.py
  tests/test_phase14_scope.py tests/test_context_router.py
  tests/test_authority_resolver.py tests/test_phase10_summarizer_anomaly.py
  -q` — **187 passed, 2 warnings**.
- `.venv\\Scripts\\python.exe -m pytest tests -q` — **1436 passed, 4 skipped,
  2 warnings** in **325.17s**.
- Critical flake8 selectors `E9,F63,F7,F82` on
  `scripts/search-api.py` and `tests/test_w25_http_scope.py` — **PASS**.
- `compileall` on the remediation Python files — **PASS**.
- `git diff --check` on the `1f428d3` production diff and `39e3c7b` test diff —
  **PASS**. The broader report-only documentation history retains intentional
  Markdown hard-break whitespace.
- AST route inventory confirmed scope authorization calls on `/search`,
  `/rank`, `/memories` list/direct lookup, `/digest`, `/anomalies`, all graph
  content routes and `/chat`; middleware covers operational and derived-state
  routes according to the accepted route matrix.

The two dependency deprecation warnings are from the installed FastAPI/
Starlette TestClient integration and did not affect results.

## Remaining limits and rollback

W-25 defines a trusted local/admin bearer boundary; it does not authenticate a
human identity or provide multi-tenant identity management. Derived graph
visibility depends on the projection's `source_memory` provenance edge and
fails closed when that edge is absent. `/graph/stats` remains an aggregate
operational surface with the existing middleware policy and does not return
entity names or memory content.

Reverting `39e3c7b` and then `1f428d3` removes the remediation without a data
migration. The canonical memory and graph stores are not rewritten by that
revert.

## Final verdict

The prior project-derived graph-node leak is closed at the HTTP response
boundary. The fresh default/global/project/all matrix, relationship and
traversal checks, graph/analyze chat checks, no-mutation probe, authorization
privacy tests, regression suite and static gates provide sufficient evidence
for **SHIP** at `9496b3eac39b29a3ad8ceb9b09687ddae4441cd3`.
