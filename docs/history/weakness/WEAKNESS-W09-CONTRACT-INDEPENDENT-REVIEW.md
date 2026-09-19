# W-09 Contract Independent Read-Only Review

**PACKAGE:** W-09 — Evaluation Evidence Integrity & Gate Semantics  
**CONTRACT REVISION:** `1fa2a0bd80e6c4c80e2f88aee8e925b0b1f23b88`  
**REVIEW TYPE:** Independent read-only contract review  
**PHASE 20:** FROZEN / LOCKED  
**V2:** SHADOW

## Scope and boundedness

- The package is limited to the production-independent evaluation boundary:
  case safety semantics, report/status validation, runner gate output,
  baseline reconciliation, IG01-C source reconciliation, and IG01-D source
  reconciliation.
- Generic Phase 15 reports are explicitly limited to strict status/privacy
  handling. They remain `legacy` or `unavailable`, are excluded from the
  verified exit gate, and cannot become promotion evidence under W-09.
- The contract excludes retrieval, embeddings, semantic providers, extraction,
  correction, lifecycle algorithms, canonical persistence, V2 promotion and
  Phase 20.
- Corpus labels, thresholds, denominators, historical baseline artifacts and
  holdout labels are protected.

## Evidence and acceptance review

- Applicable `unsupported` invariants are required to remain non-passing at
  both case and aggregate levels; `not_applicable` remains distinct.
- The top-level `evaluation_status` shape is fixed for newly generated
  generic, IG01-C and IG01-D reports, including safety, quality, capability,
  evidence, measurement and promotion states.
- IG01-C source reconciliation is bounded to the exact three-file allowlist:
  `evals/ig01c/engine.py`, `evals/ig01c/contracts.py`, and
  `evals/ig01c/metrics.py`.
- IG01-D keeps its exact existing `_CODE_PATHS` plus public corpus boundary;
  HOLDOUT remains excluded and public read guards are required.
- The stale/tampered/invalid/unavailable matrix is deterministic and requires
  self-consistent false source metadata to fail closed as `tampered`.
- Timing fields are explicitly diagnostic telemetry: finite and non-negative
  when present, but excluded from deterministic payload equality so natural
  reruns do not become false tamper failures.
- Historical schema-version-1 reports remain readable through a legacy path;
  historical baseline files are not silently rewritten.
- Existing IG01-C case rows, nine safety gates, near-zero thresholds,
  anti-gaming controls, and corpus labels remain protected.

## Prior FIX-FIRST findings and closure

The previous independent reviews identified four blockers:

1. IG01-C was absent from the implementation surface. It is now explicitly
   included with focused tests and bounded source-only changes.
2. The IG01-C source allowlist was not fixed. It is now the exact three-file
   list above, with a fixed framed SHA-256 construction.
3. Stale versus tampered classification was open-ended. Section 5.4 now
   fixes the first-applicable status matrix and gate effects.
4. Timing telemetry could cause false tamper results. Section 5.5 now excludes
   timing from deterministic equality while retaining validation of its shape.

The generic-report source ambiguity is explicitly resolved by narrowing the
contract: generic reports remain legacy/unavailable and are excluded from
verified and promotion evidence rather than receiving an implementation-defined
allowlist.

## Open state

No production implementation has started under this contract. Implementation
still requires the user's explicit authorization after this independent
contract review. The implementation author must not issue the final package
verdict.

## Verdict

**SHIP**

The W-09 contract is bounded, source-specific where it makes verification
claims, explicit about legacy generic reports, and reviewable at exact revision
`1fa2a0b`.
