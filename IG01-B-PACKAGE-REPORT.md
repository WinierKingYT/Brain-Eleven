# IG01-B Package Report — Corpus & Ground Truth

**PACKAGE:** IG01-B  
**REVISION:** `6cb4e2b584addf7ac66aa5330266c80db096c5c2` (reviewed exact head)
**OBJECTIVE:** Build a versioned, answerability-aware, privacy-safe corpus and ground truth for IG01-C without changing production intelligence.

## Scope decision

This package contains only corpus data, schema/integrity helpers, private-path
guards, failure ingestion format, documentation and CI checks. It does not add
an evaluator, alter retrieval/extraction weights, add an embedding provider,
promote V2, or change Phase 20.

## Files changed

- `IG01-B-CORPUS-CONTRACT.md`
- `IG01-B-PRIOR-ART.md`
- `evals/ig01b/schema.py`
- `evals/ig01b/generator.py`
- `evals/ig01b/annotator_b.py`
- `evals/ig01b/integrity.py`
- `evals/ig01b/private.py`
- `evals/ig01b/failures.py`
- `evals/ig01b/public/ig-eval-v2/**`
- `evals/ig01b/failures/manifest.json`
- `tests/test_ig01b_corpus.py`
- `.github/workflows/test.yml`
- `README.md`, `PROJECT-STATUS.md`, `DOCUMENTATION-AUTHORITY.md`,
  `IG01-B-INDEPENDENT-REVIEW.md`

## Root causes addressed

The existing PRE-15 corpora did not provide a single IG01-A-compatible schema,
explicit answerability set, 17-phenomenon × three-language coverage,
double-labeled holdout, pinned holdout bytes, a local realistic-corpus boundary,
or a sanitized real-failure ingestion contract. Existing `test` splits also did
not provide the required `validation` split.

## Corpus evidence

- `PUBLIC_SYNTHETIC`, version `ig-eval-v2`: **153 answerable** cases, **17
  phenomena × 3 languages × 3 cases**, split into `dev=76`, `validation=38`,
  `holdout=39`.
- Separate abstention set: **6 unanswerable** cases; excluded from normal
  precision/recall denominators and reserved for safe-abstention evaluation.
- Holdout labels: two annotator records plus adjudicated label per case;
  disagreement rate **0.0** for this synthetic seed.
- Holdout SHA-256 is pinned in `evals/ig01b/integrity.py`, the manifest and
  `holdout.sha256`; any byte change fails the integrity check.
- Public secret scan: **0 hits**.
- Private repository leakage candidates: **0**; private storage is ignored
  `evals/private/` and recursively rejects raw-content fields.
- Sanitized real-failure manifest: **0 cases**, explicitly reserved for IG-08.

## Tests executed

The bundled Python runtime successfully ran compile/import sanity and the
standalone public-corpus integrity check. The local host does not expose the
pytest executable; the complete `tests/test_ig01b_corpus.py` gate is therefore
delegated to the revision-bound GitHub Validation workflow. No local pytest
result is claimed here.

## Revision-bound remote evidence

- **Validation:** [run 34318819192](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34318819192), exact head `6cb4e2b584addf7ac66aa5330266c80db096c5c2`; Ubuntu/Windows unit, IG01-B corpus integrity, integration, context privacy, evaluation/task/router/authority/compiler smoke, coverage, Phase-14 evidence, Bandit, secret, dependency and Docker gates all passed.
- **Runtime:** [run 34318819175](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34318819175), exact same head; Ubuntu and Windows runtime jobs passed. The historical PRE-13 quality job remains failed against its frozen holdout and is retained as a visible next-package intelligence limitation.
- **Reproducibility:** generator output was written to a temporary directory and matched the tracked v2 manifest and holdout SHA `8afb7d3964a806cc04d606a7e49891f1fed53d72fd06b01c1e5dbd13c8504fa1`.

## Acceptance fields

- **LOCAL TESTS:** PASS — exact-head compile/import, public integrity, private
  boundary, sanitized-failure boundary and deterministic regeneration checks.
- **REMOTE CI:** PASS — Validation `34318819192` at exact head.
- **RUNTIME CI:** PASS — runtime Ubuntu/Windows jobs in `34318819175`; the
  historical PRE-13 quality failure is retained separately.
- **SECURITY:** PASS — Bandit, secret, dependency and Docker gates.
- **CLIENT TRUST:** NOT APPLICABLE to IG01-B corpus work; no client or runtime
  configuration was changed.
- **QUALITY FAILURE RETAINED:** PRE-13 frozen holdout quality job remains
  visible as a later evaluator/intelligence limitation.
- **OPEN P0:** none. **OPEN P1:** none for IG01-B.

## Quality metrics before / after

| Measure | Before IG01-B | After implementation |
| --- | --- | --- |
| IG01-A-compatible corpus schema | absent | present and fail-closed |
| Phenomenon/language matrix | absent | 51/51 cells, minimum 3 |
| Explicit answerability set | absent | 6 abstention cases |
| Holdout double labels | absent | 39/39, disagreement 0.0 |
| Immutable holdout bytes | manifest-only | pinned SHA + sidecar + CI |
| Private→repo leakage guard | absent | path/content guard + CI |

No production precision, recall, extraction or retrieval score is reported in
IG01-B; those belong to IG01-C and later packages.

## Safety metrics

Public secret/PII pattern hits: **0**. Private-to-repository leakage: **0**.
Raw prompt/transcript/memory fields are rejected recursively by private and
failure ingestion. Canonical MemoryStore, StateStore, ProjectRegistry and V2
runtime paths are unchanged; Phase 20 remains `FROZEN / LOCKED` and V2 remains
`SHADOW`.

## Known limitations

- The public seed is deterministic synthetic data, not dogfood data; realistic
  private cases are intentionally still empty.
- The two holdout labels use separate blind annotation passes, implementations
  and identities; this deterministic synthetic seed happens to agree on every
  case. This is process-level independence for generated fixtures, not human
  annotator agreement. Human/dogfood disagreement will be added through the
  IG-08 failure corpus.
- Full evaluator metrics, baseline snapshots and tuning are explicitly deferred
  to IG01-C.

## Open failures

No open IG01-B P0/P1 failure remains. The historical PRE-13 holdout quality
failure remains visible and is not reclassified by this data package; it is a
later evaluator/intelligence concern.

## Independent review

Independent read-only review: [IG01-B independent review](IG01-B-INDEPENDENT-REVIEW.md)
checked exact head `6cb4e2b584addf7ac66aa5330266c80db096c5c2`, corpus/schema,
evidence-derived annotator B, holdout pin/tag, privacy boundaries, prior-art,
CI and package scope. Verdict: **SHIP**. The synthetic double-label agreement
is process-level independent code-path evidence, not human annotator agreement;
that limitation remains recorded above.

## Score before / after

Evaluation quality: **4/10 → 9/10** for the contract/corpus foundation. This
does not increase task understanding, extraction, correction, retrieval,
context or daily-use intelligence scores; those remain unchanged until their
own packages produce evidence.

## Verdict

**SHIP**. IG01-C evaluator implementation, production intelligence work,
V2 promotion and Phase 20 remain closed.
