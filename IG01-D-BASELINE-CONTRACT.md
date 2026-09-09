# IG01-D — Baseline Measurement Contract

**Status:** CURRENT / ACTIVE
**Package:** IG-01 Product Evaluation Foundation, bounded baseline measurement
**Boundary:** measurement only; no production tuning or runtime promotion

## Objective

Measure the existing V1 SessionStart compiler path and the V2 shadow compiler
on the same exact, deterministic public retrieval corpus. The result is a
revision-bound comparison that makes the current quality, safety and runtime
baseline visible before any extraction, correction or retrieval change.

## Frozen inputs

| Input | Contract |
|---|---|
| Corpus | `phase15-corpus-v2` under `evals/corpus-v2` |
| Public split | `dev` + `test` only (IG01-D names these DEV + VALIDATION) |
| HOLDOUT | Never read or executed by the IG01-D runner |
| Fixture | `evals/fixtures/phase15-contract.json` |
| Seed | `17` |
| Noise count | `24` |
| Evaluator | `ig01c-1.0.0` normalized report semantics |
| Providers | `context_compiler_baseline_v1` (V1), `context_compiler_v2` (V2 shadow) |

The IG01-B `ig-eval-v2` corpus remains the extraction/reference corpus. It is
not silently substituted for this retrieval runner because the existing V1/V2
adapters consume the Phase 15 `GoldenTask` fixture shape. The corpus identity,
split mapping and fingerprints are explicit in every report.

## Required evidence

The runner emits one content-free report per provider and one paired report.
Reports contain stable task and memory identifiers, metrics, invariant states,
elapsed measurement and SHA-256 fingerprints. Prompts, transcripts, memory
content, secrets and tokens are rejected recursively by the report validator.

The pair validator refuses:

- any suite other than public;
- any split other than exactly `dev`, `test`;
- a holdout task identifier;
- differing fixture, task IDs, seed, noise count, corpus fingerprint or source
  fingerprint between V1 and V2;
- a non-full revision SHA;
- raw-content fields in nested evidence.

The normalized provider contract does not expose token counts. This remains
explicit as `budget_measurement` and is not replaced with an invented value.
Elapsed total and mean per-case timings are recorded; p50/p95 are explicit
`null` until a provider-level timing contract exists.

## Feasibility probe

`evals.ig01d.spike` is a throwaway, production-independent probe over exactly
50 DEV cases. It never reads HOLDOUT and never treats hash vectors or the
production heuristic as semantic evidence. If a real embedding plus
cross-encoder pair is unavailable, the result is `SEMANTIC_UNAVAILABLE` with
the provider and reason retained. A detected package alone is not reported as
a measured ceiling.

The probe must not change production dependencies, provider selection, weights,
extraction rules, correction behavior or V2 rollout. A measured ceiling, when
available in a future throwaway spike, will derive package targets using:

```
target = max(program_floor + margin, baseline + realistic_gain)
```

with program floors of precision `0.60`, mandatory recall `0.80` and MRR
`0.85`. The stretch values `0.75 / 0.90 / 0.85` are not silently treated as
current acceptance thresholds.

## Acceptance gate

IG01-D is `SHIP` only when both baseline reports are honest and revision-bound,
the same-input and no-HOLDOUT checks pass, the feasibility result is recorded,
quality failures remain visible, and an independent reviewer returns `SHIP`.
If the real-provider probe cannot be executed, that limitation remains an open
quality item; it does not authorize tuning, V2 promotion or Phase 20 work.

