# IG R3 D0 Decision Evidence

PACKAGE: D0
IMPLEMENTATION_REVISION: 5deebe8574276e335a3502baead6ea6875479d6a
EVIDENCE_FILE: evals/ig01d/d0-probe-real.json

OBJECTIVE:
De-risk the R1 retrieval ceiling before selecting a RETHINK branch. The probe is evaluation-only: no production retrieval wiring, ranking tuning, V2 promotion, IG-04/IG-05 work, or Phase 20 work was performed.

D0-1 SCOPE AUDIT:
- Status: PASS.
- The semantic probe candidate set uses the same current-project-plus-global scope boundary as the baseline.
- Global fixture records with an empty project identifier are normalized to global for the audit.
- wrong_project_leakage=0 for mpnet_scope_filtered and mpnet_hybrid.
- forbidden_leakage=0, superseded_leakage=0, resolved_leakage=0 for both measured variants.
- The previous R1-a leakage count of 51 was an evidence-audit normalization bug, not observed cross-project retrieval.

D0-2 CORPUS BALANCE:
- IG01-B public DEV contains 76 answerable PUBLIC_SYNTHETIC cases.
- Explicit language strata: EN=25, TR=26, TR-EN=25.
- Minimum language fraction is 0.328947, so the >=25% language-strata requirement passes.
- The planned >=100-case target is not met because the immutable DEV split contains 76 cases. No cases were invented or borrowed from HOLDOUT.
- The IG01-D retrieval fixture contains 70 public DEV cases, but no explicit language field. Deterministic prompt bucketing yields EN=58, TR=5, TR-EN=7. This fixture metadata limitation prevents a valid balanced multilingual retrieval claim.
- D0-2 status: CASE_COUNT_BELOW_TARGET; language balance is healthy in IG01-B, while the retrieval fixture needs explicit language metadata or a larger versioned split.

D0-3 RETRIEVAL-TUNED MODEL SPIKE:
- R1-compatible local MPNet embedding plus mmarco cross-encoder was available and measured on all 70 IG01-D DEV cases with seed=17 and noise_count=24.
- Retrieval-tuned candidates were attempted offline:
  - intfloat/multilingual-e5-large + cross-encoder/mmarco-mMiniLMv2-L12-H384-v1: UNAVAILABLE, local_embedding_init_failed.
  - BAAI/bge-m3 + BAAI/bge-reranker-v2-m3: UNAVAILABLE, local_embedding_init_failed.
- No network model download was attempted. No synthetic vectors were used.
- E5 query/passage prefix support is implemented in the throwaway probe but could not be scored without the local model.

| Variant | Cases | Context precision | Mandatory recall | MRR | Noise ratio |
| --- | ---: | ---: | ---: | ---: | ---: |
| mpnet_scope_filtered | 70 | 0.220000 | 0.671429 | 0.395238 | 0.780000 |
| mpnet_hybrid (RRF with V1 lexical selection) | 70 | 0.171429 | 0.728571 | 0.399286 | 0.828571 |

Per-language metrics are recorded in the evidence JSON. For the retrieval fixture bucket, mpnet_scope_filtered precision is EN=0.224138, TR=0.240000, TR-EN=0.171429. Hybrid precision is EN=0.175862, TR=0.200000, TR-EN=0.114286. These buckets are directional only because the fixture has no explicit language labels.

D0 INTERPRETATION:
- Scope correction makes the comparison valid and removes the previous false leakage signal.
- On the 70-case fixture, MPNet semantic precision is 0.22, below the R3 0.45 rethink threshold and the 0.60 program floor.
- Hybrid RRF increases mandatory recall from 0.671429 to 0.728571, but lowers precision from 0.220000 to 0.171429 and does not reduce noise.
- Retrieval-tuned E5/BGE evidence is unavailable in the offline cache, so no tuned-model ceiling can be claimed.
- The measured current-model ceiling remains below target; the final D1 branch decision is intentionally not issued because D0-2 sample size and D0-3 tuned-model availability gates are incomplete.

VALIDATION:
- D0 helper tests: 3 passed.
- Full repository regression at the exact implementation revision: 835 passed, 2 warnings, 80.83s.
- D0 probe compile/import sanity: PASS.
- Evidence content-free scan: PASS.
- HOLDOUT_INCLUDED: false.
- All variants report production_mutation=false.

OPEN FAILURES:
- IG01-B DEV has 76 rather than the planned >=100 balanced cases.
- IG01-D retrieval fixtures lack explicit language metadata.
- Retrieval-tuned E5/BGE models are absent from the offline cache.
- D0-3 therefore remains partial; no production retrieval conclusion is authorized.

VERDICT:
D1_BLOCKED
D0-1 is shipped and D0-2 language balance is confirmed, but the sample-size and tuned-model gates are not complete. Keep Phase 20 FROZEN / LOCKED, V2 SHADOW, and do not open IG-04 through IG-09. The next bounded action is to version a >=100 balanced retrieval fixture and install/provide one retrieval-tuned local model, then rerun this exact probe.
