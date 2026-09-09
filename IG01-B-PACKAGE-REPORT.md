# IG01-B Package Report — Corpus & Ground Truth

**PACKAGE:** IG01-B  
**REVISION:** pending implementation commit (exact SHA will be recorded before review)  
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
- `PROJECT-STATUS.md`, `DOCUMENTATION-AUTHORITY.md`

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

Until the final exact commit has green remote corpus CI and an independent
read-only review, IG01-B remains **FIX-FIRST / NOT ACCEPTED**. Historical PRE-13
holdout quality failures remain visible and are not reclassified by this data
package.

## Independent review

Pending. Reviewer must inspect this contract, all generated files, hash pin,
privacy boundary, CI job, prior-art report and package scope from the exact
commit, and return only `SHIP`, `FIX-FIRST` or `RETHINK`.

## Score before / after

Evaluation quality: **4/10 → pending review**. Other intelligence scores are
unchanged by this package.

## Verdict

**FIX-FIRST / NOT ACCEPTED** until exact-revision CI and independent review are
complete. IG01-C and all production intelligence work remain closed.
