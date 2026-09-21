# W-25 HTTP Scope Authorization — Independent Review

**Implementation under review:** `65510c32d246ed2dc047e27c071294d8f5d85f3f`<br>
**Review base:** `cac3df8c0daa35093605e244a49e0c4d54c51d4e` (the one-line contract-status documentation update after the implementation; production behavior is unchanged)<br>
**Contract:** accepted at `d7d4283`<br>
**Reviewer mode:** read-only review; no production code or standing untracked files changed<br>
**Verdict:** **FIX-FIRST**

## Review scope and method

I independently inspected the accepted W-25 contract, the implementation diff,
all FastAPI route declarations and signatures, the shared ProjectRegistry and
scope-filter authorities, the graph projection and chat consumers, and the
focused tests. I used the codebase knowledge graph for architecture and
relationship discovery, then read the exact checked-out source and ran fresh
tests and a synthetic two-project HTTP probe. Existing package reports were
treated as claims to verify, not as review evidence.

The implementation diff is confined to `scripts/search-api.py` and tests:
`tests/test_search_api.py`, `tests/test_w08d_search_api_lifecycle.py`,
`tests/test_w13_project_root_id_scope.py`, and
`tests/test_w25_http_scope.py`. No MemoryStore, ProjectRegistry,
`memory_scope.filter_memories`, graph implementation, retrieval weights,
compiler, V2, or Phase 20 file changed in the W-25 implementation commit.

## What passes

The HTTP boundary has one `_authorize_http_scope` helper. It is called before
loading content by `/search`, `/rank`, `GET /memories`, direct memory lookup,
`/digest`, `/anomalies`, all three graph content routes, and `/chat` (source
sites are `scripts/search-api.py:542`, `:595`, `:683`, `:797`, `:1163`,
`:1189`, `:1221`, `:1243`, `:1270`, and `:1315`). Project IDs are bounded and
checked through the existing registry, requiring `status == "active"` and
`proactive_capture is True` (`scripts/search-api.py:358-382`). The helper grants
`all` only from the middleware's validated configured API key and emits fixed
codes without the supplied project label or credential
(`scripts/search-api.py:400-429`).

The middleware uses the exact case-insensitive loopback set
`127.0.0.1`, `::1`, and `localhost`; non-loopback values, including wildcard
binds, fail closed for protected requests without a configured key
(`scripts/search-api.py:318-335`, `:475-498`). Public health and documentation
paths remain available. The route matrix includes the operational and derived
state endpoints through the middleware, including `/embed`, `/cache/clear`,
`/graph/rebuild`, `/graph/stats`, `/status`, `/metrics`, and `/cache/stats`.

Direct memory lookup filters the loaded corpus before matching the ID, so a
foreign or missing project context returns the existing content-free 404
shape. `/anomalies` receives the already filtered memory list, and ordinary
anomaly chat is explicitly content-free because the legacy handler otherwise
loads the whole vault. Denied `all` requests and unknown project requests are
performed before corpus or graph loading. The focused read-only test observed
no revision, canonical-file, graph-file, or cache-byte changes.

Independent test and static results:

- `.venv\\Scripts\\python.exe -m pytest tests/test_w25_http_scope.py tests/test_search_api.py tests/test_w08d_search_api_lifecycle.py tests/test_w13_project_root_id_scope.py -q`: **100 passed, 2 warnings**.
- `.venv\\Scripts\\python.exe -m pytest tests/test_phase14_scope.py tests/test_authority_resolver.py tests/test_context_router.py tests/test_phase10_summarizer_anomaly.py tests/test_phase11_graph_chat.py tests/test_graph_projection_revision.py -q`: **141 passed**.
- Critical flake8 selectors `E9,F63,F7,F82` on every changed Python file: **pass**.
- `compileall` on every changed Python file: **pass**.
- `git diff --check` for the implementation commit: **pass**.

The package report additionally records `1435 passed, 4 skipped, 2 warnings`
for the full suite at the implementation revision. That result was not
rerun during this bounded independent review; it does not cure the isolation
failure below.

## Blocking finding

### P1 — Graph entity enumeration leaks project-derived entities

`GET /graph/entities` delegates the response directly to
`KnowledgeGraph.find_entities` with the authorized project and retrieval
scope (`scripts/search-api.py:1221-1231`). The canonical graph's
`_node_allowed` correctly filters memory and project nodes, but returns `True`
for every other node type (`brain_eleven/graph/projection.py:297-317`). The
entity extractor creates technology and phase nodes from each memory without
attaching project provenance (`brain_eleven/extraction/entities.py:234-245`).

This makes the HTTP scope decision appear to succeed while the response still
contains names derived solely from another project. The same unprovenanced
nodes are visible in the no-project default/global view, which is required to
be global-only. Chat graph/analyze intents inherit the same leak because
`ChatAgent._find_subject_entities` calls the graph filter and then uses the
returned entity (`brain_eleven/runtime/chat_interface.py:354-395`).

Fresh probe, using a temporary vault with active/proactive projects `a` and
`b`, one global memory, an `a` memory mentioning Redis, and a `b` memory
mentioning PostgreSQL:

```text
GET /graph/entities                         -> 200, includes tech_postgresql
GET /graph/entities?project_id=a            -> 200, includes tech_postgresql
GET /graph/entities?project_id=a&name_contains=PostgreSQL
                                             -> 200, [tech_postgresql]
POST /chat {"message":"show graph PostgreSQL","project_id":"a"}
                                             -> 200, "'PostgreSQL' has no recorded relationships."
```

The project-B memory node and its secret content are filtered, but the
project-B-derived technology name and its presence are disclosed. The W-25
focused fixture only uses `GLOBAL_VISIBLE`, `PROJECT_A_SECRET`, and
`PROJECT_B_SECRET`, none of which produce a technology or phase node, so its
graph assertions do not exercise this boundary.

This fails the contract's project isolation and default/global-only graph
requirements even though the ordinary memory, search, rank, digest, anomaly,
direct-ID, and `all` key checks pass. The implementation cannot claim SHIP
until the HTTP response is restricted to nodes with demonstrably authorized
provenance (or unprovenanced derived nodes are suppressed for scoped/default
requests). Any fix must remain within the W-25 HTTP boundary or be separately
contracted; silently changing the canonical graph authority would violate the
accepted package scope.

## Gate disposition

| Gate | Independent disposition | Evidence |
|---|---|---|
| 1. Boundary/identity | **FAIL** | One helper and API-key/registry checks are present, but graph enumeration and graph chat do not prove project isolation for derived nodes. |
| 2. Adapter/route-only | PASS | Implementation diff is limited to the authorized HTTP adapter and tests; canonical authorities and CAS/write paths are untouched. |
| 3. Parity/safety tests | **FAIL** | Fresh graph probe leaks a project-B-derived node to project A and the default view; focused tests lack a project-specific derived-entity fixture. |
| 4. Full verification | PARTIAL | Independent focused/regression/static checks pass; the separately recorded full-suite result was not rerun here. |
| 5. Independent review | Complete | This read-only review records the blocking finding and verdict. |

## Required follow-up before acceptance

Add a focused fixture where project A, project B, and global memories produce
distinct technology/phase nodes. Assert that default/global and project-A
`/graph/entities` responses contain no project-B-derived names, and exercise
the graph/analyze chat intents with the same query. Then rerun the W-25,
scope/authority/graph regression, full-suite, flake8, compileall, and diff
checks at the fixed revision. Recheck that unknown/archived/disabled project
denials and denied reads remain content-free and read-only.

## Rollback and final verdict

Reverting the W-25 implementation commit
`65510c32d246ed2dc047e27c071294d8f5d85f3f` restores the prior HTTP route
behavior without a data migration. Because a scoped/default graph request can
still disclose a project-derived entity name, W-25 is **FIX-FIRST**. This
review does not modify production code.
