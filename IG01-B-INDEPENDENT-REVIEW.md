# IG01-B Independent Acceptance Review

**Status:** REVIEW / SHIP  
**Reviewed revision:** `6cb4e2b584addf7ac66aa5330266c80db096c5c2`  
**Reviewer:** independent read-only reviewer (`/root/ig01b_reviewer`)  
**Review date:** 2026-09-09

## Scope

The review covered the IG01-B contract, current diff, public corpus and
manifest, holdout pin/tag, evidence-derived annotator B, private and sanitized
failure boundaries, prior-art report, CI topology and package boundary. It did
not authorize IG01-C, production intelligence tuning, V2 promotion or Phase 20
work.

## Evidence checked

- `ig-eval-v2`: 153 answerable cases, 17 phenomena × 3 languages, `dev=76`,
  `validation=38`, `holdout=39`, plus 6 separate abstention cases.
- Holdout SHA `8afb7d3964a806cc04d606a7e49891f1fed53d72fd06b01c1e5dbd13c8504fa1`
  matches manifest, sidecar, integrity constant and immutable tag
  `ig01b-corpus-v2`.
- Annotator B is a separate implementation that receives only case evidence
  (family, query, conversation role/text and candidate IDs), never category or
  annotator A's primary label object.
- Private and sanitized-failure writers enforce root/nested allowlists,
  bounded tokens/hashes and recursive raw-content rejection. The sanitized
  failure manifest remains empty and reserved for IG-08.
- [Validation run 34318819192](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34318819192)
  passed the required unit, corpus, integration, privacy, smoke, coverage and
  security gates. [Runtime run 34318819175](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/34318819175)
  passed Ubuntu and Windows runtime jobs.
- The historical PRE-13 quality failure remains visible and is not counted as
  an IG01-B corpus failure.

## Findings

Scope is clean: no evaluator, retrieval/extraction tuning, provider migration,
V2 promotion or Phase 20 change is present. `evals/intelligence_taxonomy.py`
remains shared IG-00 vocabulary only. Phase 20 is `FROZEN / LOCKED` and V2 is
`SHADOW`.

The synthetic holdout's zero disagreement is a limitation of generated,
independent code-path labels; it is not human-annotator agreement. The package
report records this limitation and reserves real disagreement mining for IG-08.

## Verdict

**SHIP**
