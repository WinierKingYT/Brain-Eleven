# W-25 HTTP Project-Scope and Authorization Contract — Independent Re-review 03

**Review type:** independent, read-only contract re-review
**Contract:** `WEAKNESS-W25-HTTP-SCOPE-AUTHORIZATION-CONTRACT.md`
**Contract blob SHA:** `10adda35461033816941d366253b8a49896d1f0a`
**Contract commit:** `215587fce253338b2498f0b02fab3dd572284ebb`
**Reviewed repository HEAD:** `215587fce253338b2498f0b02fab3dd572284ebb`
**Review date:** 2026-09-16
**Production/contract changes:** none

## Review boundary

This is a fresh independent review of the corrected W-25 contract. The
previous `FIX-FIRST` findings were checked against the exact current contract
and the current route definitions. No production file or contract was edited;
standing untracked workspace evidence was not staged.

## Corrections verified

- The `/anomalies` content-bearing route is explicitly identified at contract
  lines 73-77, included in the scoped-read matrix at line 92, and covered by
  the filtered-or-content-free requirement in lines 97-100 and Gate 3 lines
  257-263. The cited implementation still confirms the need:
  `scripts/search-api.py:981-993` calls the whole-vault detector and
  `brain_eleven/support/anomaly.py:213-245` returns detector details that may
  contain content excerpts.
- The route matrix now includes every current FastAPI endpoint. In particular,
  `GET /graph/stats` is explicitly classified with aggregate/operational reads
  at contract line 91. `/embed`, `/cache/clear` and `/graph/rebuild` remain
  explicitly classified at lines 94-95 and covered by Gate 3 lines 271-273.
- Privacy scope is correctly limited to W-25 denial responses, denial logs and
  new scope/auth telemetry at lines 203-215. Existing successful query/path
  responses and unrelated legacy catch-all errors are clearly recorded as
  out of scope, avoiding a conflict with the current API behavior.
- Loopback semantics are deterministic at lines 158-166: only
  `127.0.0.1`, `::1` and case-insensitive `localhost` are accepted; wildcard
  hosts and all other values are non-loopback and require the fail-closed
  sensitive-route policy unless a key is configured.

## Contract and gate assessment

The bounded objective preserves MemoryStore, ProjectRegistry,
`memory_scope.filter_memories`, graph projection, retrieval, canonical writes,
V1/V2 selection and Phase 20. The authorization helper requirements cover
default/global, validated project, admin `all`, archived/disabled/corrupt
registry states, direct-ID lookup, and non-loopback startup behavior. The
route matrix and Gate 3 cover the complete content, aggregate, processing and
derived-state mutation surfaces. Privacy, no-side-effect denial checks and
bounded revert behavior are testable. The explicit deferral of per-user
multi-tenant identity is a stated limitation rather than an undocumented
assumption for this local trusted API.

The cited code references remain accurate at this exact repository head. No
remaining P0, P1 or P2 contract gap was found in the requested areas.

## Decision

**VERDICT: SHIP**

The W-25 contract is accepted for implementation review at the exact contract
blob SHA above. This review authorizes only the separately bounded W-25
implementation described by the contract; it does not authorize retrieval
tuning, V2 promotion, Phase 20 work or changes to canonical authorities.
Phase 20 remains FROZEN / LOCKED and V2 remains SHADOW.
