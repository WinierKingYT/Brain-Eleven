# IG R3 D0 Decision Evidence

PACKAGE: D0
IMPLEMENTATION_REVISION: 0fb8d00f3776bf004796c54a52689fb439532c01
EVIDENCE_FILE: evals/ig01d/d0-probe-real-exact.json

OBJECTIVE:
Complete the R3 de-risk probe without changing production retrieval, canonical authority, V2 rollout, or Phase 20. The probe uses a versioned public-synthetic multilingual fixture, explicit sidecar language labels, current-project-plus-global scope filtering, and a local retrieval-tuned embedding spike.

D0-1 SCOPE AUDIT:
- Status: PASS.
- The semantic and hybrid variants apply the current-project-plus-global scope boundary.
- Empty project identifiers are normalized to global for the audit.
- wrong_project_leakage=0, forbidden_leakage=0, superseded_leakage=0, and resolved_leakage=0 for every measured variant.
- The previous R1-a leakage count of 51 was an evidence-audit normalization bug, not observed cross-project retrieval.

D0-2 CORPUS BALANCE:
- A new immutable public-synthetic fixture `ig-r3-d0-v1` was generated from public DEV and TEST cases only; HOLDOUT was excluded.
- The fixture contains 120 distinct task identities with explicit sidecar language metadata: EN=40, TR=40, TR-EN=40.
- Minimum language fraction is 0.333333, and the >=100-case requirement passes.
- The IG01-B reference DEV remains 76 answerable cases with balanced 25/26/25 strata; it is recorded as a reference limitation and was not silently changed.
- D0-2 status: PASS for the retrieval probe fixture.

D0-3 RETRIEVAL-TUNED MODEL SPIKE:
- Current MPNet embedding plus the existing mmarco cross-encoder was measured on all 120 cases.
- `intfloat/multilingual-e5-large` was available locally and measured with the required `query:` / `passage:` prefixes, using the same mmarco cross-encoder.
- No production provider or ranking configuration was changed. All variants report production_mutation=false.

| Variant | Cases | Context precision | Mandatory recall | MRR | Noise ratio |
| --- | ---: | ---: | ---: | ---: | ---: |
| mpnet_scope_filtered | 120 | 0.205000 | 0.704167 | 0.484583 | 0.795000 |
| mpnet_hybrid (RRF) | 120 | 0.185000 | 0.804167 | 0.480833 | 0.815000 |
| tuned_scope_filtered (E5-large) | 120 | 0.190000 | 0.641667 | 0.460972 | 0.810000 |
| tuned_hybrid (E5-large + RRF) | 120 | 0.201667 | 0.812500 | 0.473194 | 0.798333 |

Per-language metrics, provider provenance, hashed case identities, and all safety counters are recorded in the evidence JSON. Each language has exactly 40 cases.

D0 INTERPRETATION:
- The scope correction removes the previous false leakage signal.
- The balanced fixture and tuned-model gates are now complete.
- The best measured precision is 0.205000 (MPNet scope-filtered); tuned hybrid reaches 0.201667 and does not approach the R3 0.45 rethink threshold or the program 0.60 floor.
- Tuned hybrid improves mandatory recall to 0.812500, but precision remains low and noise remains 0.798333.
- The corrected empirical ceiling is therefore below 0.45. D1 selects Branch B; no Branch A continuation is authorized.

VALIDATION:
- Balanced corpus generator: 120 cases, schema validation PASS, language counts 40/40/40.
- D0 helper and corpus tests: PASS.
- Full repository regression at the exact implementation revision: 836 passed, 2 warnings, 79.32s.
- D0 probe compile/import sanity: PASS.
- Evidence content-free scan: PASS.
- HOLDOUT_INCLUDED: false.
- All variants report production_mutation=false.

OPEN FAILURES:
- Retrieval precision remains below the R3 rethink threshold on both current and tuned stacks.
- The IG01-B reference DEV remains 76 cases; the new D0 fixture is the balanced retrieval measurement surface.
- Production retrieval must not be tuned or promoted from this result.

D1 DECISION:
BRANCH_B

The embedding-similarity retrieval approach is not graduated. IG-04 through IG-09 remain closed until a separately approved Branch B design is implemented and measured. The R3 plan's recommended next bounded design is B1 semi-automatic memory: keep autonomous capture, present ranked candidates for human confirmation, and remove direct automatic retrieval injection. This report does not implement that product change.

PROGRAM STATE:
Phase 20 remains FROZEN / LOCKED. V2 remains SHADOW. No Phase 20 work, production retrieval wiring, extraction tuning, correction work, or architecture rewrite was performed.
