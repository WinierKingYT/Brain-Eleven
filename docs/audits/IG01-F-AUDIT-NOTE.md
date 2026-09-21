# IG01-F Phase 0 Audit Note — Naive Recency Baseline

**Status:** STOP / OWNER DECISION REQUIRED

**Package:** IG01-F only

**Audit head:** `a93e54215d09be5af13ce718810a6bb955a60e10`

**Branch:** `ig/ig01f-naive-baseline`

**Boundary:** read-only Phase 0; no selector, evaluator, IG01-D, threshold,
skip/xfail, V2 SHADOW, corpus, or HOLDOUT content change

## Preconditions

- The branch point is the exact current `origin/master` head,
  `a93e54215d09be5af13ce718810a6bb955a60e10`.
- [Validation run 35659909356](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/35659909356)
  is the latest master run at that SHA. `Unit tests (ubuntu-latest)` and `Unit
  tests (windows-latest)` both passed. The overall workflow is red because the
  separate `IG01-E independent evaluation audit` job failed at its
  revision-bound audit step; this is not an artifact-upload 403 and is not
  relabelled as infrastructure success. IG01-F's stated precondition is limited
  to the two unit jobs, so Phase 0 proceeded.
- `python -m evals.baseline_snapshot --baseline baseline-v2 --check` passed and
  reported `status=current`, 130 cases, context precision `0.18`, and context
  recall `0.8038461538461539`.
- The working tree was clean before this docs-only audit commit. No HOLDOUT
  content or sidecar was opened. Only public documentation, executable code,
  DEV/VALIDATION inputs, and the public manifest metadata were inspected.

## Provider registration and invocation

The assumed command exists, but provider registration is a closed list rather
than a pluggable interface:

- `evals/run.py:23-28` defines suites; `public` maps to `dev` + `test`, while
  `holdout` and `all` are separate explicit suite choices.
- `evals/run.py:60-92` accepts only `baseline`, `router`, `authority`, and
  `compiler-v2`, builds one Phase-15 synthetic vault, and invokes
  `provider.select(task, vault.root)`.
- `evals/run.py:124-143` repeats the same closed provider choices in the CLI.
- V1 is `BaselineContextProvider` (`evals/baseline.py:153-180`). It deliberately
  does not pass task text to the compiler (`evals/baseline.py:158-163`) and
  normalizes the result to the existing `NormalizedEvaluationResult`
  (`evals/baseline.py:119-150`).
- V2 is `CompilerV2ContextProvider` (`evals/compiler_v2_provider.py:32-85`). It
  does consume the task prompt, runs Router -> Authority -> Compiler V2, and
  normalizes selected memory IDs to the same result shape.

A `recency_continuity` arm can only be added by changing `evals/run.py` and the
provider/evidence code. That is mechanically possible without changing IG01-C
formulas, but it cannot satisfy the requested comparison merely by registering
another provider because of the budget and corpus incompatibilities below.

## IG01-D pairing and evidence

- The accepted contract freezes `phase15-corpus-v2`, DEV + TEST, fixture
  `phase15-contract`, seed 17, noise 24, evaluator `ig01c-1.0.0`, and V1/V2
  provider identities (`docs/contracts/IG01-D-BASELINE-CONTRACT.md:14-30`).
- The runner recomputes both providers on the same public inputs
  (`evals/ig01d/baseline.py:397-440`) and emits strict per-provider plus paired
  evidence (`evals/ig01d/baseline.py:442-476`). The CI artifact is
  `ig01d-baseline-evidence` containing `ig01d-baseline-pair.json` and JUnit
  evidence (`.github/workflows/test.yml:162-194`).
- Evidence is content-free and rejects suite/split/provider/source drift and
  HOLDOUT identifiers (`docs/contracts/IG01-D-BASELINE-CONTRACT.md:32-64`).
- The no-HOLDOUT proof is executable: public validation visits only `dev` and
  `test` (`evals/ig01d/baseline.py:45-69`), the public fingerprint visits only
  those directories (`evals/ig01d/fingerprint.py:45-62`), and the runner rejects
  task IDs containing `holdout` (`evals/ig01d/baseline.py:411-416`).
- The accepted report records V1 precision/recall `0.172308/0.765385`, V2
  `0.147210/0.488462`, zero four-class leakage, and
  `SEMANTIC_UNAVAILABLE` because no real embedding plus cross-encoder pair was
  available (`docs/history/reports/IG01-D-PACKAGE-REPORT.md:19-25`).

## IG01-C evaluator contract

IG01-C defines retrieval precision@K, recall@K, mandatory recall, F1, MRR,
noise/token waste, context precision and mandatory coverage
(`docs/contracts/IG01-C-EVALUATOR-CONTRACT.md:55-78`). Its absolute-zero gates
include forbidden, wrong-project, superseded, and resolved leakage
(`docs/contracts/IG01-C-EVALUATOR-CONTRACT.md:86-103`). Mandatory select-all and
select-none controls make recall-only/select-everything strategies visible
through precision, noise and token waste
(`docs/contracts/IG01-C-EVALUATOR-CONTRACT.md:105-115`). These formulas and gates
must remain unchanged.

## Corpus metadata

The public `ig-eval-v2` manifest declares 153 answerable cases, 17 phenomena,
languages `en`, `tr`, and `tr-en`, 76 DEV / 38 VALIDATION / 39 HOLDOUT cases,
and six separate abstention cases
(`evals/ig01b/public/ig-eval-v2/manifest.json:14-57`; see also
`docs/contracts/IG01-B-CORPUS-CONTRACT.md:27-49`). Phase 0 inspected only the
manifest metadata and DEV/VALIDATION records. The 17 phenomenon labels are:
`explicit_decision`, `preference`, `lesson`, `requirement`, `suggestion`,
`hypothetical`, `question`, `negation`, `correction`, `quoted_material`,
`assistant_proposal`, `old_critical_decision`, `irrelevant_recent_memory`,
`wrong_project_candidate`, `superseded_memory`, `resolved_blocker`, and
`ambiguous_reference`.

This corpus is not the IG01-D runner corpus. Its public DEV + VALIDATION portion
contains extraction, reference-resolution, and retrieval families in JSONL
conversation records, whereas `evals.run` loads Phase-15 GoldenTask JSON files
and builds a canonical synthetic vault (`evals/run.py:45-92`). IG01-D explicitly
states that `ig-eval-v2` is not silently substituted because its adapters consume
the Phase-15 GoldenTask fixture shape
(`docs/contracts/IG01-D-BASELINE-CONTRACT.md:27-30`). Therefore the requested
17-phenomenon/per-language comparison cannot be obtained through the accepted
IG01-D provider path without a new, separately contracted corpus-to-vault and
family-mapping boundary.

## Canonical read paths and scope safety

- V1 loads the canonical `MemoryStore` document and resolves typed project state
  through `StateResolver` (`scripts/context-compiler.py:112-140`).
- Its ranking calls the shared `filter_memories` with current project and default
  retrieval scope, then accepts only active records
  (`scripts/context-compiler.py:442-464`). The stable package re-exports the one
  canonical scope implementation (`brain_eleven/memory/scope.py:1-37`).
- The typed read-only state boundary is `StateResolver`; corrupt/unavailable
  authority fails closed (`brain_eleven/state/resolver.py:1-32` and
  `scripts/context-compiler.py:125-140`). V1 renders active requirements and
  blockers from that resolved state.
- The native scoped V1 adapter loads the same canonical snapshot, uses the same
  ranking/state primitives, and supplies empty related-note, Last Session, and
  Open Loops inputs (`brain_eleven/runtime/context.py:48-91`). This matches
  `RUNTIME-DATAFLOW.md:23-30`: unscoped Last Session, Open Loops, and linked-note
  inputs are deliberately excluded and must not be reintroduced.

No closer scope-safe canonical analogue was found that would justify changing
the frozen default selector rule without owner confirmation.

## Budget audit — STOP

The equal-budget comparison is undefined in the accepted IG01-D interface:

- IG01-D itself records `budget_measurement` as "token counts unavailable in
  normalized provider contract" for each provider and for the pair
  (`evals/ig01d/baseline.py:336-343`, `465-469`; contract explanation at
  `docs/contracts/IG01-D-BASELINE-CONTRACT.md:55-58`).
- The evaluated V1 adapter calls the legacy compiler's public `compile()` with
  no caller-owned token/byte budget (`evals/baseline.py:153-180`). That compiler
  selects a fixed top five (`scripts/context-compiler.py:653-701`).
- The evaluated V2 adapter uses `BudgetContract(2048,
  minimum_headroom_tokens=128)` (`evals/compiler_v2_provider.py:54-56`).
- A shared conservative estimator exists and measures UTF-8 bytes with
  `ceil(bytes / 3) + 1` (`context_compiler_v2/tokenizer.py:21-40`), and the
  native scoped V1 runtime path uses it with a default 3000-token cap
  (`brain_eleven/runtime/context.py:54-118`). That native path is not the V1
  provider measured by IG01-D, so substituting it would change the comparison
  contract and evidence identity.

Consequently there is neither one common frozen budget profile nor two declared
IG01-D profiles at which all three arms can be compared. Inventing a cap after
this audit would violate the instruction to use the exact IG01-D budget profile,
and modifying IG01-D is forbidden.

## STOP decision and required owner resolution

Two Phase 0 STOP conditions apply:

1. Budgets differ in a way that makes equal budget undefined: fixed top-five V1
   versus 2048/128 V2, with no IG01-D budget measurement or common rendered-size
   contract.
2. The required 17-phenomenon `ig-eval-v2` report cannot be hosted by the
   existing Phase-15 provider path without introducing a new corpus/family and
   vault-fixture adapter contract. Doing so inside IG01-F without owner choice
   would silently redefine the accepted IG01-D comparison.

Per the work order, work stops here. No `IG01-F-PREREGISTRATION` was created, no
phenomenon classification was frozen, and no selector implementation, tests,
measurement, evidence, CI job, or package report was produced. In particular,
no measurement was run and no HOLDOUT file was loaded, read, or scored.

The owner must choose and separately authorize both: (a) the equal-budget
contract (for example, a new common rendered-context budget applied to V1, V2,
and recency without altering preserved IG01-D evidence), and (b) whether IG01-F
uses the Phase-15 retrieval corpus for direct V1/V2 comparability or introduces
a reviewed `ig-eval-v2` retrieval/vault projection capable of the requested 17
phenomenon and three-language breakdown. Existing IG01-D evidence must remain
immutable either way.
