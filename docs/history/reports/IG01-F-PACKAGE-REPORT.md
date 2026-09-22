# IG01-F Package Report — Naive Recency Baseline

**Status:** SECOND REVIEW REMEDIATION IMPLEMENTED / INDEPENDENT RE-REVIEW REQUIRED

**Acceptance:** Not self-approved. Remote exact-head Validation and a separate
read-only `SHIP / FIX-FIRST / RETHINK` review remain required.

## Boundary and revisions

- Branch point: `a93e54215d09be5af13ce718810a6bb955a60e10`.
- Frozen pre-registration: `2b18372` (before provider, runner, and evidence).
- Original measurement-source revision: `f486009341577d32392d2fa8d136b4f27155e5f2`.
- Hardened validator/test revision: `3e379bd887a51b90cbe626dc87562317f9effc21`;
  rebound evidence revision: `4fca188`; CI definition revision: `81fbbd3`.
- IG01-E path-regression prerequisite: merged from `origin/master` at
  `9200a7506b47249e0b145f693fc7b40b51aea666`; integration revision
  `b295c0a97308e47c00b4a83d4568f2c0e18b3982`.
- Corpus: `ig01f-recency-v1`, public DEV + VALIDATION only (114 cases), plus
  six public abstention cases. `holdout_included=false`.
- Source fingerprint:
  `sha256:806a4a80c893462a7392c09f7e55f0074fbb30ac84754334af6ab1e41a1345db`.
- Budget: 2048 maximum conservative tokens, 128 headroom, 1920 usable,
  24,000 rendered UTF-8 bytes.

No IG01-D file, evaluator threshold, skip/xfail, production V2 behavior, or
canonical write authority changed. The provider reads canonical MemoryStore and
typed StateStore surfaces and remains evaluation-only.

## Changed files

- `evals/ig01f/provider.py`: deterministic, query-blind, scope/lifecycle-safe,
  budget-bound `recency_continuity` provider.
- `evals/ig01f/corpus.py` and `evals/ig01f/public/ig01f-recency-v1/**`:
  deterministic public-only canonical-store projection.
- `evals/ig01f/measure.py` and
  `evals/ig01f/ig01f-naive-baseline-evidence.json`: strict source-bound runner,
  per-case evidence, IG01-C select-all/select-none controls, and frozen result.
- `tests/test_ig01f_recency.py`: determinism, query blindness, budget, scope,
  lifecycle, read-only, HOLDOUT, schema, fingerprint, tamper, and anti-gaming
  checks.
- `.github/workflows/test.yml`: separate Ubuntu and Windows regeneration/check
  jobs and evidence artifacts.
- `docs/audits/IG01-F-AUDIT-NOTE.md` and
  `docs/contracts/IG01-F-PREREGISTRATION.md`: Phase 0 findings, owner resolution,
  frozen rules, classification, and decision meanings.

## Aggregate measurement

All values are macro means over the 114 public answerable cases. Token waste is
present in per-case evidence but not applicable because the immutable projected
candidate metadata does not claim reference token counts.

| Provider | P@5 | R@5 | F1 | MRR | Noise | Mandatory recall | Context precision |
|---|---:|---:|---:|---:|---:|---:|---:|
| V1 | 0.105263 | 0.895522 | 0.298507 | 0.776119 | 0.587719 | 0.895522 | 0.350877 |
| V2 | 0.040351 | 0.343284 | 0.114428 | 0.313433 | 0.057018 | 0.343284 | 0.162281 |
| Recency | 0.105263 | 0.895522 | 0.298507 | 0.843284 | 0.587719 | 0.895522 | 0.350877 |

The recency arm has zero forbidden, wrong-project, superseded, and resolved
leakage over the full measurement.

## Language strata

| Stratum / provider | P@5 | R@5 | F1 | MRR | Noise | Mandatory recall | Context precision |
|---|---:|---:|---:|---:|---:|---:|---:|
| en / V1 | 0.105263 | 0.909091 | 0.303030 | 0.750000 | 0.592105 | 0.909091 | 0.355263 |
| en / V2 | 0.063158 | 0.545455 | 0.181818 | 0.477273 | 0.118421 | 0.545455 | 0.223684 |
| en / Recency | 0.105263 | 0.909091 | 0.303030 | 0.863636 | 0.592105 | 0.909091 | 0.355263 |
| tr / V1 | 0.100000 | 0.863636 | 0.287879 | 0.750000 | 0.592105 | 0.863636 | 0.328947 |
| tr / V2 | 0.021053 | 0.181818 | 0.060606 | 0.181818 | 0.000000 | 0.181818 | 0.105263 |
| tr / Recency | 0.100000 | 0.863636 | 0.287879 | 0.818182 | 0.592105 | 0.863636 | 0.328947 |
| tr-en / V1 | 0.110526 | 0.913043 | 0.304348 | 0.826087 | 0.578947 | 0.913043 | 0.368421 |
| tr-en / V2 | 0.036842 | 0.304348 | 0.101449 | 0.282609 | 0.052632 | 0.304348 | 0.157895 |
| tr-en / Recency | 0.110526 | 0.913043 | 0.304348 | 0.847826 | 0.578947 | 0.913043 | 0.368421 |

## Per-phenomenon metrics

These are the existing evaluator metrics recorded in the frozen evidence; no
derived or post-hoc metric was added. `—` means the metric is not applicable
because that phenomenon has no relevant retrieval target in the projected
retrieval view; this is preserved rather than coerced to zero.

### V1
| Phenomenon | Cases | P@5 | R@5 | F1 | MRR | Noise | Mandatory recall | Context precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ambiguous_reference | 6 | 0.000000 | — | — | — | 1.000000 | — | 0.000000 |
| assistant_proposal | 7 | 0.000000 | — | — | — | 1.000000 | — | 0.000000 |
| correction | 6 | 0.200000 | 1.000000 | 0.333333 | 0.833333 | 0.500000 | 1.000000 | 0.500000 |
| explicit_decision | 6 | 0.200000 | 1.000000 | 0.333333 | 0.916667 | 0.500000 | 1.000000 | 0.500000 |
| hypothetical | 7 | 0.000000 | — | — | — | 1.000000 | — | 0.000000 |
| irrelevant_recent_memory | 6 | 0.200000 | 1.000000 | 0.333333 | 1.000000 | 0.000000 | 1.000000 | 1.000000 |
| lesson | 7 | 0.200000 | 1.000000 | 0.333333 | 0.928571 | 0.500000 | 1.000000 | 0.500000 |
| negation | 7 | 0.000000 | — | — | — | 1.000000 | — | 0.000000 |
| old_critical_decision | 7 | 0.200000 | 1.000000 | 0.333333 | 0.714286 | 0.500000 | 1.000000 | 0.500000 |
| preference | 7 | 0.200000 | 1.000000 | 0.333333 | 0.714286 | 0.500000 | 1.000000 | 0.500000 |
| question | 7 | 0.000000 | — | — | — | 1.000000 | — | 0.000000 |
| quoted_material | 7 | 0.000000 | — | — | — | 1.000000 | — | 0.000000 |
| requirement | 7 | 0.200000 | 1.000000 | 0.333333 | 0.714286 | 0.500000 | 1.000000 | 0.500000 |
| resolved_blocker | 7 | 0.200000 | 1.000000 | 0.333333 | 1.000000 | 0.000000 | 1.000000 | 1.000000 |
| suggestion | 6 | 0.000000 | — | — | — | 1.000000 | — | 0.000000 |
| superseded_memory | 7 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| wrong_project_candidate | 7 | 0.200000 | 1.000000 | 0.333333 | 1.000000 | 0.000000 | 1.000000 | 1.000000 |

### V2
| Phenomenon | Cases | P@5 | R@5 | F1 | MRR | Noise | Mandatory recall | Context precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ambiguous_reference | 6 | 0.000000 | — | — | — | 0.000000 | — | 0.000000 |
| assistant_proposal | 7 | 0.000000 | — | — | — | 0.000000 | — | 0.000000 |
| correction | 6 | 0.033333 | 0.166667 | 0.055556 | 0.166667 | 0.083333 | 0.166667 | 0.083333 |
| explicit_decision | 6 | 0.100000 | 0.500000 | 0.166667 | 0.500000 | 0.166667 | 0.500000 | 0.333333 |
| hypothetical | 7 | 0.000000 | — | — | — | 0.000000 | — | 0.000000 |
| irrelevant_recent_memory | 6 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| lesson | 7 | 0.028571 | 0.142857 | 0.047619 | 0.142857 | 0.071429 | 0.142857 | 0.071429 |
| negation | 7 | 0.000000 | — | — | — | 0.000000 | — | 0.000000 |
| old_critical_decision | 7 | 0.057143 | 0.285714 | 0.095238 | 0.142857 | 0.142857 | 0.285714 | 0.142857 |
| preference | 7 | 0.085714 | 0.428571 | 0.142857 | 0.285714 | 0.214286 | 0.428571 | 0.214286 |
| question | 7 | 0.000000 | — | — | — | 0.000000 | — | 0.000000 |
| quoted_material | 7 | 0.000000 | — | — | — | 0.285714 | — | 0.000000 |
| requirement | 7 | 0.085714 | 0.428571 | 0.142857 | 0.428571 | 0.000000 | 0.428571 | 0.428571 |
| resolved_blocker | 7 | 0.200000 | 1.000000 | 0.333333 | 1.000000 | 0.000000 | 1.000000 | 1.000000 |
| suggestion | 6 | 0.000000 | — | — | — | 0.000000 | — | 0.000000 |
| superseded_memory | 7 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| wrong_project_candidate | 7 | 0.085714 | 0.428571 | 0.142857 | 0.428571 | 0.000000 | 0.428571 | 0.428571 |

### Recency
| Phenomenon | Cases | P@5 | R@5 | F1 | MRR | Noise | Mandatory recall | Context precision |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| ambiguous_reference | 6 | 0.000000 | — | — | — | 1.000000 | — | 0.000000 |
| assistant_proposal | 7 | 0.000000 | — | — | — | 1.000000 | — | 0.000000 |
| correction | 6 | 0.200000 | 1.000000 | 0.333333 | 1.000000 | 0.500000 | 1.000000 | 0.500000 |
| explicit_decision | 6 | 0.200000 | 1.000000 | 0.333333 | 1.000000 | 0.500000 | 1.000000 | 0.500000 |
| hypothetical | 7 | 0.000000 | — | — | — | 1.000000 | — | 0.000000 |
| irrelevant_recent_memory | 6 | 0.200000 | 1.000000 | 0.333333 | 1.000000 | 0.000000 | 1.000000 | 1.000000 |
| lesson | 7 | 0.200000 | 1.000000 | 0.333333 | 1.000000 | 0.500000 | 1.000000 | 0.500000 |
| negation | 7 | 0.000000 | — | — | — | 1.000000 | — | 0.000000 |
| old_critical_decision | 7 | 0.200000 | 1.000000 | 0.333333 | 0.500000 | 0.500000 | 1.000000 | 0.500000 |
| preference | 7 | 0.200000 | 1.000000 | 0.333333 | 1.000000 | 0.500000 | 1.000000 | 0.500000 |
| question | 7 | 0.000000 | — | — | — | 1.000000 | — | 0.000000 |
| quoted_material | 7 | 0.000000 | — | — | — | 1.000000 | — | 0.000000 |
| requirement | 7 | 0.200000 | 1.000000 | 0.333333 | 1.000000 | 0.500000 | 1.000000 | 0.500000 |
| resolved_blocker | 7 | 0.200000 | 1.000000 | 0.333333 | 1.000000 | 0.000000 | 1.000000 | 1.000000 |
| suggestion | 6 | 0.000000 | — | — | — | 1.000000 | — | 0.000000 |
| superseded_memory | 7 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 | 0.000000 |
| wrong_project_candidate | 7 | 0.200000 | 1.000000 | 0.333333 | 1.000000 | 0.000000 | 1.000000 | 1.000000 |

## Paired and abstention results

- Recency vs V1 by per-case F1: **0 wins / 114 ties / 0 losses**.
- Recency vs V2 by per-case F1: **37 wins / 77 ties / 0 losses**.
- Six-case abstention set: V2 emitted six empty selections; V1 and Recency
  emitted none. This is expected for the query-blind continuity arms and is a
  visible limitation, not reclassified as successful abstention.

## Pre-registered decisions

- **S passes.** On the 48 recency-hostile cases Recency context precision is
  `0.197917`, noise is `0.802083`, and MRR is `0.730769`, versus `0.500000`,
  `0.500000`, and `1.000000` on the 26 recency-favorable cases. The expected
  hostile degradation is visible; no leakage/evaluator-audit stop is triggered.
- **F1 applies:** Recency exceeds V2 aggregate precision and recall. On this
  derived corpus, V2 is not shown to add value over recency. No tuning was done.
- **F2 applies:** Recency ties V1 on aggregate precision, recall, F1, mandatory
  recall, noise, and context precision, and exceeds it on MRR. This corpus does
  not demonstrate additional V1 selection value over the naive arm.
- **F3 applies:** On the four recency-favorable phenomena, Recency macro F1 is
  `0.333333` while V2 macro F1 is `0.128205`. This is a suspected V2 regression
  for owner triage; it is not fixed in IG01-F. Follow-up is recorded in
  [issue #2](https://github.com/WinierKingYT/Brain-Eleven/issues/2), which
  deliberately does not authorize tuning.

## Verification

- `python -m evals.baseline_snapshot --baseline baseline-v2 --check`: PASS.
- `pytest tests/test_ig01f_recency.py -q`: 12 passed.
- Evidence regeneration followed by `--check`: byte-identical locally.
- Full local non-integration/non-graduation regression at documentation head
  `4672f93`: 1478 passed, 4 skipped, 82 deselected. The four skips are
  pre-existing suite markers; IG01-F adds no skip/xfail. An initial run while
  status/authority files were still uncommitted produced five expected
  W06C0R1 worktree-scope failures plus one transient cold-hook failure; the
  affected 24-test slice passed after the docs commit, and the full rerun above
  was green.
- Historical pre-remediation Validation at `c19316e`: PASS in
  [run 35740598678](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/35740598678).
  It is retained as history, not claimed as validation of the current head.
- Second-review remediation adds deterministic full-payload validation,
  nested metric/paired tamper rejection, an explicit provider-level forbidden
  fixture, and a runner-wide no-HOLDOUT-open sentinel. Focused suite: 15 passed;
  evidence regeneration check: byte-identical after rebinding source identity.
- Current final-head remote Validation: pending at this documentation commit.
  The terminal exact SHA/run pair is recorded as closure evidence on issue #2,
  avoiding an endless report-URL/commit cycle.
- Independent read-only re-review: pending; this report is not acceptance.

## Limitations and owner questions

The corpus is synthetic, derived from multi-family public cases, intentionally
recency-hostile, and contains no real-use data. Each case has at most two
canonical candidates, so the generous common budget often admits the complete
safe candidate set; the main V1/Recency difference is ranking (MRR), not set
membership. The comparison therefore strongly supports the recorded finding
inside this fixture but does not estimate live-user utility. V1 and Recency also
do not abstain on the separate abstention set.

Owner follow-ups after independent acceptance: decide through issue #2 whether
F3 warrants a separate V2 investigation package, and whether a future separately pre-registered
real-use or denser-candidate corpus is worth measuring. Neither is authorized
inside IG01-F.
