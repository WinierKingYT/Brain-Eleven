# W-25 HTTP Project-Scope and Authorization Contract — Independent Review

**Review type:** independent, read-only contract review  
**Contract:** `WEAKNESS-W25-HTTP-SCOPE-AUTHORIZATION-CONTRACT.md`  
**Contract blob SHA:** `b04453beb229dce0ce012280a40656dfdc021f0d`  
**Contract commit:** `6bad4d376cc5d917bd4ba42a11d15888e5434c1c`  
**Reviewed repository HEAD:** `6bad4d376cc5d917bd4ba42a11d15888e5434c1c`  
**Review date:** 2026-09-16  
**Production/contract changes:** none

## Review boundary

This review checked the contract's code references, bounded objective, route
matrix, threat model, acceptance gates, privacy requirements and rollback
description against the current `scripts/search-api.py`, its actual support
modules and the existing API tests. The contract and production files were
not edited. The existing untracked workspace evidence was left untouched.

## Verified claims

The principal references and the recorded original failure are accurate:

- `scripts/search-api.py:122-133` defines the request scope selectors;
  `:354-445`, `:494-524`, `:955-979`, `:1006-1067` and `:1092-1111`
  consume them.
- `scripts/search-api.py:608-625` scans the complete memory list for a direct
  ID and has no request project/scope context.
- `scripts/search-api.py:300-313` makes the API-key gate conditional on
  `BRAIN_ELEVEN_API_KEY`; without a configured key, non-public routes proceed.
- `scripts/search-api.py:1154-1175` only warns about a missing key and passes
  the host to Uvicorn; it does not fail closed.
- `scripts/memory_scope.py:230-257` permits `all` without a project ID and
  returns every input record for that scope.
- The existing project filtering tests and API-key tests are correctly cited
  at `tests/test_search_api.py:138-196` and `:549-590`, and do not cover the
  proposed two-project authorization matrix.

The proposed direct-ID rules, registry validation, API-key requirement for
`all`, no-key/non-loopback gate, bounded error codes, read-only denial checks,
and revert-without-data-migration direction are clear and useful. The
five-gate structure is also suitable for an implementation package.

## Findings

### P1 — `/anomalies` is an existing unscoped content-bearing route omitted from the gate

The contract classifies `/anomalies` with operational/aggregate surfaces at
lines 80-83 and therefore excludes it from the scope-bearing route list at
lines 61-78. Gate 3 likewise requires authorization tests for search, rank,
memory listing, digest, graph entity routes and chat at lines 231-246, but no
`/anomalies` case.

The current route is content-bearing, not merely aggregate:

- `scripts/search-api.py:981-993` calls `AnomalyDetector.detect_all()` over
  the whole vault and accepts no project or scope context.
- `brain_eleven/support/anomaly.py:213-245` scans every memory.
- Detector results include memory content excerpts or full short content in
  `:86-89`, `:110-116`, `:130-133`, `:150-153`, `:190-193` and `:203-207`.
- With no API key, the middleware at `scripts/search-api.py:305-313` allows
  the request.

Thus an ordinary local HTTP caller can receive snippets from every project
through `/anomalies`, even if the W-25 implementation correctly rejects
`retrieval_scope=all` on the listed routes. This leaves the same class of
project-isolation failure open under the contract's stated objective.

**Required contract correction:** classify `/anomalies` explicitly. Either
require the same authorized project/admin context and add the two-project
privacy tests, or make the response content-free/redacted and test that
choice. The route must not remain an unscoped exception hidden under
"operational or aggregate" wording.

### P1 — Privacy requirement is broader than the bounded implementation surface and is internally ambiguous

Lines 180-189 say that bodies and logs must not echo raw query text, memory
content, vault paths, untrusted project labels or exception tracebacks. If
this applies to all W-25 API responses/logs, the current code contradicts it
outside the proposed read-boundary helper:

- `scripts/search-api.py:362` logs the raw search query and `:398-402`
  returns it in the normal search response.
- `:339-345` returns the configured vault path from `/status`.
- Several existing catch-all handlers return exception text, including
  `:409-410`, `:525-527`, `:977-979` and `:1082-1084`.

If the intended rule is only for authorization failures and new bounded
telemetry, that scope must be stated explicitly; otherwise an implementer
cannot satisfy both the privacy rule and the existing normal response
contract without widening W-25. The acceptance tests currently mention
malformed scope/project errors only and do not resolve this ambiguity.

**Required contract correction:** define the exact response/log classes to
which the no-echo rule applies, and either add the existing surfaces to W-25
or explicitly record them as pre-existing out-of-scope behavior.

### P2 — The route matrix does not classify every actual endpoint

The contract names most routes, but `/embed` (`scripts/search-api.py:452-488`),
`POST /cache/clear` (`:942-949`) and `POST /graph/rebuild` (`:1069-1084`)
are absent from the explicit route policy. The latter two mutate derived
state/cache and are currently reachable without a key when the key is unset;
`/embed` is a non-memory content-processing surface. The contract's
non-loopback rule refers to "sensitive routes" without defining whether these
three are included. A complete matrix should state, for every method/path,
whether it is public, ordinary scoped, admin-only, aggregate-only or outside
this package, and what happens with no key on loopback and non-loopback.

### P2 — Loopback policy needs an exact host definition

Lines 139-150 require a non-loopback host to fail closed but do not define the
accepted loopback values or wildcard/container semantics. The current
`docker-compose.yml:19-26` deliberately sets `BRAIN_ELEVEN_HOST=0.0.0.0`
while publishing the host port on loopback and permits an empty API key. The
contract says Docker networking is outside scope, so the implementation and
tests need an explicit decision for `127.0.0.1`, `::1`, `localhost` and
`0.0.0.0`; otherwise the same deployment may be treated as safe or unsafe
depending on a string check.

## Threat-model assessment

The contract covers the primary observed threats: unauthenticated `all`,
direct-ID exposure, project/scope mismatch, registry corruption, key absence
on non-loopback, untrusted query parameters, bounded errors and cache/read
side effects. It correctly limits the package to the HTTP boundary and keeps
canonical authorities and retrieval algorithms unchanged.

The `/anomalies` omission is a material threat-model gap because it exposes
stored content without any selector. The incomplete route matrix also makes
the status of mutating operational endpoints under the host/key policy
unclear. Per-user multi-tenant authorization is explicitly deferred by the
contract; that is acceptable as a stated limitation for this local trusted
API, provided it remains documented.

## Acceptance, privacy and rollback assessment

The five gates are otherwise testable. Gate 3 should be amended for
`/anomalies`, the three unclassified endpoints, and the clarified privacy
scope. The rollback statement (revert the W-25 code commit, no data
migration, no unauthenticated compatibility switch) is bounded and safe in
principle, but the final package report should identify the complete commit
range if implementation is split across commits.

## Decision

The contract accurately captures the original direct-ID/`all` defect, but it
does not yet close the full HTTP content boundary it claims to govern. The
unscoped `/anomalies` route is a P1 gap, and the privacy wording is ambiguous
against existing response/log behavior.

**VERDICT: FIX-FIRST**

Implementation is not authorized by this review. Update the contract and
obtain a fresh independent contract review before writing W-25 production
code. Phase 20 remains FROZEN / LOCKED and V2 remains SHADOW.
