# IG01-D Package Report — Paired Baseline Measurement

**Status:** ACCEPTED / HUMAN CHECKPOINT PASS
**Verdict:** SHIP

This package records the first revision-bound V1/V2 comparison. It measures
the existing providers on one frozen public corpus; it does not tune ranking,
change extraction, add an embedding provider, promote V2, or open Phase 20.

| Field | Evidence |
|---|---|
| **PACKAGE** | IG01-D — Paired V1/V2 Baseline Measurement |
| **REVISION** | `61c89e9934f669b5c624e5e1a921cd62e4f49b04` (exact implementation/test head producing the evidence below; documentation closure is recorded separately) |
| **OBJECTIVE** | Produce reproducible, content-free V1/V2 evidence with identical inputs, explicit no-HOLDOUT proof, a bounded semantic-feasibility probe, and derived targets. |
| **FILES CHANGED** | `.github/workflows/test.yml`; `evals/ig01d/{__init__,baseline,contracts,fingerprint,spike}.py`; `tests/test_ig01d_baseline.py`; `IG01-D-BASELINE-CONTRACT.md`; `IG01-EVALUATION-FOUNDATION.md`; `DOCUMENTATION-AUTHORITY.md`. |
| **ROOT CAUSES ADDRESSED** | No paired revision-bound baseline; no explicit corpus/split fingerprint; no guarded target derivation; no content-free evidence contract; no explicit semantic-provider unavailability result. |
| **TESTS ADDED** | Pair/schema validation, strict bounded metadata, complete safety/comparison evidence, same-input identity, public-only fingerprint, raw-content rejection, target-formula integrity, and 50-case DEV-only feasibility-boundary tests. |
| **TESTS EXECUTED** | Local `compileall` PASS; exact-head paired runner and 16 contract probes PASS; remote Validation #197 required jobs PASS, including IG01-D paired baseline, unit (Ubuntu/Windows), integration, coverage, context privacy, evaluation smoke, Phase 16–19 smoke/evidence, Bandit, secrets, dependency and Docker security. |
| **QUALITY METRICS BEFORE** | Historical V1 compatibility report: precision `0.18`, recall `0.803846` (130 public cases). |
| **QUALITY METRICS AFTER** | V1 precision `0.172308`, context recall `0.765385`, mandatory recall `0.714286`; V2 precision `0.147210`, context recall `0.488462`, mandatory recall `0.467532`; V2 outcome `degraded`. Both providers selected the same 130 public DEV+TEST task IDs and used the same seed `17` / noise `24`. |
| **SAFETY METRICS** | V1 and V2 wrong-project, forbidden, superseded and resolved leakage rates are all `0.0`; candidate invariant gate passed with no failed or unsupported invariants. Feasibility explicitly reports `holdout_included=false`. |
| **CORPUS / SOURCE** | Corpus `phase15-corpus-v2`, fixture `phase15_contract`, split fingerprint `sha256:28f18f9f01c59db148842052b4d26046f3a1517f081b2cb34a4cbdee0bda186c`; evaluation-source fingerprint `sha256:cb284c1e52b125ba00285bc0b50b78c5e1b15e8de0cbc560539c31def1109534`; evaluator `ig01c-1.0.0`. |
| **TARGET DERIVATION** | Frozen formula `max(program_floor + margin, baseline + realistic_gain)`; margin `0.05`, gain `0.10`, floors precision `0.60`, mandatory recall `0.80`, MRR `0.85`; provisional targets precision `0.65`, mandatory recall `0.85` from the actual `required_selected_items / required_items` baseline `0.714286`, MRR `0.85` (MRR unavailable in normalized provider contract). |
| **FEASIBILITY** | `SEMANTIC_UNAVAILABLE`, provider `openai_only`; 50 DEV cases, no HOLDOUT; no empirical ceiling is claimed because no real embedding + cross-encoder pair is installed. Hash vectors are never used as semantic evidence. |
| **KNOWN LIMITATIONS** | V2 is weaker than V1 on this baseline; token counts and MRR are unavailable in the normalized provider contract; the throwaway semantic probe is bounded to an explicit unavailable result until a real local/cloud embedding plus cross-encoder pair is provisioned. Historical PRE-13 runtime quality remains a visible failure. |
| **OPEN FAILURES** | No IG01-D P0/P1. V2 degradation and semantic-provider unavailability remain recorded inputs for later intelligence packages; they do not authorize tuning in IG01-D. |
| **INDEPENDENT REVIEW** | `SHIP`, score `9/10`, returned by the separate read-only reviewer for exact SHA `61c89e9`. Self-review was not used as acceptance. |
| **SCORE BEFORE** | Evaluation quality `4/10` (program estimate). |
| **SCORE AFTER** | `9/10` for measurement instrumentation per independent review; no extraction/retrieval/product-quality score is raised by this package. |
| **HUMAN CHECKPOINT** | `IG01-D human checkpoint PASS` received from the user on 2026-09-09; the package is fully accepted. |
| **VERDICT** | `SHIP` |

Remote evidence:

- [Validation #197 — exact `61c89e9`](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34343132347) — success. Ubuntu/Windows unit, integration, coverage, privacy, evaluation smoke, security and IG01-D paired-baseline jobs passed. The `ig01d-baseline-evidence` artifact was produced with digest `sha256:dcf036c8e57170f3b6c4371f73383cf936c352953f3d13f85d2ed4ba60ba6315`; master-only public/evidence jobs were correctly not applicable on this branch.
- [Runtime #58 — exact `61c89e9`](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34343132276) — Ubuntu and Windows runtime jobs and runtime/security artifacts passed. The aggregate remains failed only because the historical PRE-13 `quality` job fails; its artifact digest is `sha256:69fe16f2578b075dfb2217030e0a5ca11594fe1a750f7e9b477f796968860168` (Ubuntu runtime `sha256:733c4451638bba50c6b103952c7c4efd1e407a022fd8be0550aac70f80a855a1`, Windows runtime `sha256:4fe09c368ce42a4f0ad3bd5f9f7bde60b320b7f4688b2c85a97b03b21f1578e5`). This historical quality failure is retained and is not relabeled as an IG01-D infrastructure pass.

Client trust evidence is explicitly bounded: the repository's isolated native-hook smoke records delivery/receipt/canonical-verification telemetry without prompts, transcripts or private memory. Live Claude/Codex trust remains a user-owned checkpoint and is not claimed as verified by this report.

The paired JSON artifact is content-free: it contains identifiers, hashes,
metrics and invariant results, never prompts, transcripts, memory text,
secrets or token values. The package remains bounded to measurement. IG01-E is
now the next bounded package; IG-03 and Phase 20 remain unopened. Phase 20 is
still `FROZEN / LOCKED` and V2 is still `SHADOW`.

**Post-checkpoint hardening note:** independent audit found that the original
runner validated the complete V2 corpus before selecting DEV+TEST. The bounded
fix in commit `a3537ca2e679e7263980aa150a2e87bcef7da571` adds a public-only
validator and a read guard test. The measurements above remain bound to
`61c89e9`; a fresh exact-head pair artifact and CI evidence are required before
this hardening is considered a final D revalidation.
