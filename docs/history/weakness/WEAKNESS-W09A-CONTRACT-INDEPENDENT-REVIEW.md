# W-09A Contract Independent Review

**Reviewed revision:** `e7c42c4104e8f53c599fd73947d2c7f6dfe79b10`
**Reviewed contract:** `WEAKNESS-W09A-RETRIEVAL-EVALUATION-CONTRACT.md`
**Verdict:** `SHIP`

## Scope

This is an independent read-only review of the W-09A evaluation contract. It
does not approve implementation or retrieval changes.

## Findings

- The public corpus boundary is exact and reproducible: `evals/corpus-v2/`,
  schema version 1, corpus version 2, with direct `dev/*.json`, `test/*.json`
  and `holdout/*.json` task files. The committed manifest declares 70 DEV,
  60 TEST and 30 HOLDOUT cases, and `python -m evals.corpus_v2_builder
  --check` reports `status=current`.
- Candidate content is required to come from the deterministic fixture vault's
  canonical `validated_memory` records, with content fingerprints and an
  invalid result when referenced IDs are absent. IDs are therefore not treated
  as stand-in documents.
- The source fingerprint allowlist explicitly includes the V1 and V2
  executable surfaces, their memory/state/project dependencies, fixture
  generator, metrics/reporting/schema surfaces and focused tests. The exact
  files and deterministic POSIX `.py` globs are bounded, sorted and exclude
  symlinks and `__pycache__`; an additional source path requires a contract
  amendment.
- DEV/TEST/HOLDOUT responsibilities and the HOLDOUT read guard are explicit.
  Public measurement is limited to DEV + TEST, while HOLDOUT is read-only
  final evidence after decisions are frozen. Corpus labels and split identity
  are fingerprinted and versioned.
- Set labels are sorted, unique and bounded; ranked candidate and selected
  arrays preserve order and are independently fingerprinted. Required,
  acceptable, forbidden and mandatory subset/disjointness rules are explicit,
  as are invalid and `answerability=NO` exclusions.
- The metric formulas define precision, recall, F1, MRR, mandatory recall,
  noise ratio and token waste, including empty-set and unavailable-token
  behavior. Fixed-K overlong output is invalid, and select-all/select-none
  controls are required.
- V1/V2 equality includes cases, candidates, labels, content/order/query
  fingerprints, split/version, seed, provider configuration, normalization
  and tie-breaking. Promotion comparison requires strict precision gain,
  accepted mandatory-recall parity, zero safety leakage, verified evidence
  and measured quality.
- Provider and evidence states are bounded and distinct. Missing semantic or
  embedding capability is explicitly `unavailable` or `unsupported` with a
  reason code; stale, tampered, invalid and unavailable source states are
  preserved, block promotion and are never converted into scores.
- Privacy and exclusions are sufficient: reports are content-free, raw
  prompts/transcripts/memory text/secrets/credentials are excluded, and the
  contract forbids retrieval, embedding, lifecycle, memory-write, rollout and
  HOLDOUT-tuning changes.

No contract-level P0, safety leakage, split ambiguity, formula ambiguity,
provider-state collapse, privacy violation or unbounded input was found.

## Decision

`SHIP` — the contract is sufficiently precise and bounded to authorize the
separate W-09A implementation phase. This verdict does not claim that the
implementation or exit-gate tests have been completed; the contract itself
correctly leaves the package status as `REVIEW PENDING` until that work is
implemented and independently validated.
