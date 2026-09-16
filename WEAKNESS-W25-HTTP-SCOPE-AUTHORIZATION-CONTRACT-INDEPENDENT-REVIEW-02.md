# W-25 HTTP Project-Scope and Authorization Contract — Independent Re-review

**Review type:** independent, read-only contract re-review
**Contract:** `WEAKNESS-W25-HTTP-SCOPE-AUTHORIZATION-CONTRACT.md`
**Contract blob SHA:** `1c9208e94d9c0097401986fcd7aacac90c0f7583`
**Contract commit:** `a3733c69e0f7d73f0a8f40bb21c7c9e66d12eddc`
**Reviewed repository HEAD:** `a3733c69e0f7d73f0a8f40bb21c7c9e66d12eddc`
**Review date:** 2026-09-16
**Production/contract changes:** none

## Review boundary

This re-review checked the exact contract after the previous independent
`FIX-FIRST` result. It rechecked the earlier findings against the current
`scripts/search-api.py`, `brain_eleven/support/anomaly.py`, the route
definitions, Docker host configuration and the cited API tests. No production
file or contract was edited, and standing untracked evidence was not staged.

## Earlier findings rechecked

The previous P1 omissions were corrected in the contract:

- `/anomalies` is now identified at contract lines 73-77 as a whole-vault,
  content-bearing route. It is included in the route policy at lines 88-100,
  and Gate 3 at lines 257-263 requires either authorized filtering or an
  explicitly content-free/redacted response. This matches the current code:
  `scripts/search-api.py:981-993` calls `detect_all()` without a selector,
  while `brain_eleven/support/anomaly.py:213-245` scans the supplied memory
  list and detector details expose content at `:86-89`, `:110-116`,
  `:130-133`, `:150-153`, `:190-193` and `:203-207`.
- The earlier privacy ambiguity is narrowed at lines 203-215 to denial
  responses, their logs and new scope/auth telemetry. Existing successful
  `/search` query and `/status` vault-path responses are expressly recorded
  as out of scope, so the contract no longer conflicts with the current
  behavior at `scripts/search-api.py:362`, `:398-402` and `:339-345`.
- `/embed`, `/cache/clear` and `/graph/rebuild` are now explicitly present in
  the route matrix at lines 94-95 and in Gate 3 at lines 271-273.
- Loopback semantics are now explicit at lines 158-166: only
  `127.0.0.1`, `::1` and case-insensitive `localhost` are accepted; wildcard
  and all other values are non-loopback. This gives the implementation and
  tests a deterministic policy and accounts for the current Compose setting
  at `docker-compose.yml:19-26`.

## Remaining finding

### P2 — `GET /graph/stats` is still absent from the claimed complete route matrix

The contract says the complete route policy must be recorded at lines 85-95,
but the table has no row or entry for `GET /graph/stats`. The separate route
is real at `scripts/search-api.py:999-1004`; it calls `_ensure_graph_current()`
and returns projection/entity/relationship counts. It is also the endpoint
used by the existing API-key tests at `tests/test_search_api.py:577-590`.

Although this endpoint is aggregate rather than memory-content bearing, its
authorization class and no-key behavior still matter: `_ensure_graph_current`
reads the canonical revision and can rebuild the derived projection, and the
current middleware permits the request whenever no API key is configured.
The route therefore needs an explicit aggregate/operational classification
and the same loopback/non-loopback key decision as `/status`, `/metrics` and
`/cache/stats`, plus a denied-request side-effect assertion if it is covered
by the W-25 route matrix.

This is a contract completeness gap, not a new production defect introduced
by the re-review. The missing entry could let an implementation leave one
actual endpoint without a documented boundary policy while Gate 5 requires a
complete route matrix.

## Gate and threat-model assessment

The corrected `/anomalies` requirement now covers the prior content-leak
vector, and the updated Gate 3 contains the required two-project, denial,
non-loopback and side-effect evidence. The denial-only privacy wording and
exact host list are implementable. The contract continues to preserve
MemoryStore, ProjectRegistry, scope filtering, graph projection, retrieval
and V1/V2 boundaries, and the revert-without-data-migration path remains
bounded.

The only open review issue is the unclassified `/graph/stats` endpoint. No
new P1 issue was found in the corrected sections.

## Decision

The previous P1 findings are fixed in the contract, but the document's
explicitly claimed complete route matrix still omits a real route. Add
`GET /graph/stats` to the matrix and its acceptance policy, then obtain the
required fresh independent contract review.

**VERDICT: FIX-FIRST**

Implementation remains unauthorized by this review. Phase 20 remains FROZEN /
LOCKED and V2 remains SHADOW.
