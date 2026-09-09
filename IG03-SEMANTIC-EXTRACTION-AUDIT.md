# IG-03 — Semantic Extraction Read-only Audit

**Status:** CURRENT REVIEW — audit only; no implementation authorized by this
document

**Audit input revision:** `c2525a4d58aeae3a19715b837cc747e691f9e0c6`

**Package gate:** IG-01 is closed and shipped after the human checkpoint. Phase
20 remains `FROZEN / LOCKED`; V2 remains `SHADOW`.

## Purpose and boundary

This is the read-only reality check required before the IG-03 bounded contract.
It records what the repository actually does at the exact input revision. It
does not claim semantic extraction is implemented, does not select a provider,
and does not change the capture, truth, retrieval or runtime paths.

The package order follows the current IG execution contract: IG-03 freezes the
proposition and validation boundary before IG-02 closes the autonomous capture
pipe. IG-04 reference resolution, IG-05 retrieval quality and IG-06 V2
promotion remain closed.

## Current extraction path

The active extraction implementation is `scripts/extraction.py`:

```text
EvidenceBatch
  → DeterministicExtractor.extract
  → sentence segmentation and regex classification
  → safety screening (`capture_safety.evaluate_capture`)
  → project-scope gate
  → NewMemoryCandidate / StateMutationProposal
  → QuarantineCandidate for unsafe or non-committed material
```

The module docstring explicitly limits the extractor to reviewable proposals.
It does not resolve memory IDs, mutate lifecycle, write `MemoryStore` or
`StateStore`, or treat assistant/tool/system prose as a user commitment.
Canonical writes are therefore outside this package's current production
extraction boundary.

The deterministic classifier recognises explicit decision, current/resolved
state, requirement, lesson and preference markers. It quarantines proposals,
hypotheticals, questions, quotes, negations, low-evidence statements, unknown
project scope and explicit corrections whose target is not resolved. State
operations are typed separately from memory candidates.

## Existing value objects and frozen input schema

The production value objects currently include `Commitment`, `CandidateKind`,
`MemoryType`, `StateOperation`, `ExtractedBase`, `NewMemoryCandidate`,
`StateMutationProposal`, `QuarantineCandidate` and `ExtractionEnvelope`.
Their fields are useful compatibility inputs, but they are not the full IG-03
semantic proposition.

IG01-A froze the later projection in
`IG01-A-EVALUATION-CONTRACT.md` (`ExtractionCandidate / Proposition`):

```text
candidate_id, project_id, claim_type, subject, predicate, value,
commitment, temporal_scope, source_role, evidence_refs,
confidence_components, correction_clues, target_clues, schema_version
```

The IG-03 implementation must map into this projection without adding
unreviewed fields. A proposition remains a candidate and never becomes
canonical truth by itself.

## Safety and authority findings

* Role handling is present in `_classify_commitment`; assistant, tool and
  system messages become `PROPOSED` and are quarantined before a user memory
  candidate is returned.
* Question, hypothetical, quote, negation and uncertain paths are quarantined.
* `capture_safety.evaluate_capture` runs before candidate acceptance, and an
  unscoped message is quarantined as `SCOPE_UNRESOLVED`.
* Explicit correction currently becomes `LIFECYCLE_TARGET_UNKNOWN`; resolving
  a conversational target belongs to IG-04.
* The worker imports and applies deterministic candidates, so any new semantic
  provider must remain a proposal-only dependency and must not acquire a
  canonical writer capability.
* Existing semantic-search code correctly reports provider unavailability and
  no longer uses hash-seeded vectors in production retrieval. That embedding
  path is unrelated to IG-03 extraction and must not be silently reused as an
  extraction provider.

## Evaluation inputs available

IG01-B provides the versioned public `ig-eval-v2` corpus with extraction cases
in English, Turkish and mixed Turkish/English. The manifest records 153
answerable public cases across 17 phenomena, 76 DEV cases, 38 VALIDATION cases,
39 double-labelled HOLDOUT cases and a six-case abstention set. The holdout is
sealed and must not be read during IG-03 implementation or tuning.

IG01-C provides the production-independent `evaluate_extraction_case` metric
surface. It matches typed proposition fields, records decision precision and
recall, false commitment, assistant-as-user, wrong type/scope and ECE, and
rejects a `canonical_commit` request as a safety violation. Existing tests
cover exact decisions, semantic claim identity, assistant proposals and
direct canonical-write attempts.

The current corpus is a valid measurement input, not proof of semantic
quality. It is primarily synthetic-template data; private realistic cases and
sanitized real failures are reserved for their documented boundaries.

## Provider reality

The repository has no required semantic-extraction model dependency in
`pyproject.toml`. `scripts/embedding-generator.py` contains an optional
OpenAI embedding client for search, while `evals/ig01d/spike.py` reports
`SEMANTIC_UNAVAILABLE` unless a real provider is detected. Neither file is a
semantic extraction implementation and neither may be presented as a measured
IG-03 provider.

The contract therefore needs a provider-agnostic interface with explicit
capability and availability results. The required benchmark candidates are:

1. the existing deterministic extractor as a control baseline;
2. a local model adapter (Qwen-class or equivalent), only when installed and
   explicitly configured; and
3. a stronger optional model adapter, also explicitly configured.

Unavailable providers must produce a content-free `SEMANTIC_UNAVAILABLE`
record. Fabricated vectors, fabricated scores and network calls hidden inside
the default test path are prohibited.

## Scope decision

The following are in the IG-03 boundary: safety prefiltering before model
input, provider interface and capability reporting, semantic proposition
mapping, deterministic schema/authority/scope/temporal/confidence validation,
provider benchmark wiring and content-free evidence.

The following are explicitly out: capture queue/worker plumbing (IG-02),
reference resolution and lifecycle mutation (IG-04), retrieval/ranking and
embeddings (IG-05), V2 runtime promotion (IG-06), architecture consolidation,
new persistence authorities and Phase 20 work.

## Risks requiring contract controls

1. A model may emit valid-looking JSON with unknown or unsafe fields. Unknown
   fields must fail closed before evaluation or downstream use.
2. A model may label assistant proposals, questions or hypotheticals as
   committed. Role and commitment gates must be deterministic and absolute.
3. A project may be absent or malformed. Such propositions may be reviewed or
   quarantined but cannot be canonical candidates.
4. A model may report a scalar confidence without provenance. Component values
   and a deterministic range/sum check are required; ECE is measured, not
   assumed.
5. A provider may be unavailable or return malformed output. The result must
   be explicit and safe, never a synthetic semantic result.
6. Extraction changes can accidentally import truth or lifecycle authority.
   Import and capability tests must keep the model below the canonical write
   boundary.

## Audit conclusion

The repository has a safe deterministic proposal baseline and a frozen
proposition contract, but no production semantic extractor, provider
benchmark, semantic validator or calibrated provider evidence. IG-03 is
therefore ready for a bounded contract and implementation package; it is not
ready for a SHIP verdict. This audit records the starting truth only.

