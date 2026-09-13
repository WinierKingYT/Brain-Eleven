# W-09 — Evaluation Evidence Integrity & Gate Semantics Contract

**Status:** CONTRACT / IMPLEMENTATION NOT AUTHORIZED  
**Observed revision:** `798727e65545e8758a4bbe7657a870a0322051ad`  
**Program:** Engineering Weak-Point Improvement Goal  
**Phase 20:** FROZEN / LOCKED  
**V2 runtime:** SHADOW

This contract is a bounded correction to the evaluation evidence boundary. It
does not improve a retriever, change a corpus label, promote V2, or alter
Phase 20. Implementation may begin only after an independent review of this
contract and an explicit human authorization.

## 1. Problem statement

The repository has a useful production-independent evaluator, but its evidence
and gate vocabulary is not yet strong enough to support an engineering claim
without interpretation.

The current code establishes the following facts:

1. `CaseEvaluation.passed` returns `not self.violations` at
   `evals/metrics.py:93-115`. `violations` contains only invariants whose state
   is `fail` (`:94-97`). A case with an applicable `unsupported` capability can
   therefore serialize `passed: true`, even though the aggregate CLI gate
   rejects an `unsupported` summary at `evals/run.py:115-121`.
2. `evals/reporting.py:146-173` correctly preserves aggregate `pass`, `fail`,
   `unsupported`, and `not_applicable` states, but
   `compare_evaluation_reports()` at `:326-409` exposes only a safety-oriented
   `candidate_gate`. Quality deltas are reported, yet there is no separate
   quality status or explicit statement that a quality measurement is
   unavailable.
3. Generic report validation at `evals/reporting.py:225-310` validates shape,
   numbers, ordering, and invariant states. Its scalar `source` values are
   accepted as metadata; they are not reconciled with the repository and
   corpus that produced the report.
4. IG01-D computes `evaluation_source_fingerprint` and public split identity in
   `evals/ig01d/baseline.py:198-274`, and validates exact internal agreement in
   `evals/ig01d/contracts.py:261-530`. The validator checks that `git_sha` and
   fingerprints have the right format and agree with fields inside the report,
   but reading a report does not recompute those values from a supplied root.
   A stale or edited report can therefore remain structurally valid until an
   external comparison is performed.
5. The current-suite baseline already has a stronger reconciliation path:
   `evals/baseline_snapshot.py:78-113` recomputes the deterministic public
   result and compares it with the committed `baseline-v3` snapshot. Its
   floating-point comparison uses bounded `math.isclose` tolerances. Historical
   V1/V2 manifests remain immutable and are checked by
   `check_historical_baseline()` at `:142-190`.
6. `evals/run.py:22-29, 75-77` defines explicit `smoke`, `public`, `holdout`,
   and `all` suite boundaries. IG01-D calls the runner with `public_only=True`
   (`evals/ig01d/baseline.py:224-235`) and its feasibility probe is fixed to
   50 DEV cases with `holdout_included: false`
   (`evals/ig01d/spike.py:265-369`). These are valuable boundaries that this
   package must preserve and make visible in evidence.

The weakness is evidence ambiguity and provenance trust, not a claim that the
underlying evaluator is mathematically wrong. A green safety result must not
be read as a quality result, and a structurally valid report must not be read
as current evidence until its source is reconciled.

## 2. Objective

Make evaluation evidence explicit, revision-bound, and non-misleading while
preserving current measurement behavior and historical artifacts.

After this package, a reviewer must be able to distinguish, from the report
itself:

- whether safety invariants passed, failed, or could not be evaluated;
- whether quality was measured, unavailable, or not applicable;
- whether the provider capability required by a safety invariant was supported;
- whether the report was reconciled against the exact fixture, corpus split,
  evaluator source, revision, and run parameters that it claims; and
- whether the result is suitable for measurement only or can satisfy a future
  promotion gate.

This package must not manufacture a quality score when a provider is missing,
must not turn `unsupported` into `pass`, and must not use holdout labels to
repair or tune a public result.

## 3. Bounded scope

### 3.1 Implementation surface

The implementation agent may change only the evaluation boundary and its
tests, limited to:

- `evals/metrics.py` — case-level safety/capability semantics;
- `evals/reporting.py` — explicit status fields, report validation, and
  comparison status;
- `evals/run.py` — separate safety/quality/evidence gate reporting and exit
  semantics;
- `evals/baseline_snapshot.py` — only if needed to expose the existing
  reconciliation result; do not weaken its comparison or rewrite snapshots;
- `evals/ig01d/contracts.py`, `evals/ig01d/baseline.py`, and
  `evals/ig01d/spike.py` — only for revision/source reconciliation or bounded
  status propagation;
- focused evaluation tests and a package report/evidence document.

No production memory, capture, retrieval, router, authority, compiler, graph,
state, or task implementation is in scope.

### 3.2 Explicitly excluded

The following are outside W-09 and must not be changed as a workaround:

- retrieval ranking, embeddings, semantic providers, reranking, task-aware
  retrieval, extraction, correction, or lifecycle algorithms;
- any fixture, task label, expected memory ID, threshold, denominator, or
  holdout label;
- `baseline-v1` or `baseline-v2` reports/manifests, their provider identity, or
  their historical interpretation;
- V2 promotion, canary/default behavior, SessionStart delivery, or rollback;
- Phase 20 or any Knowledge Engine work;
- private raw prompts, transcripts, memory content, or credentials;
- changing a report to make a failing quality measurement pass;
- replacing an unavailable provider with a random, synthetic, or lexical score
  and labeling the result semantic evidence.

## 4. Frozen status model

The status model is part of this contract. Exact strings are bounded codes,
not free-form prose.

### 4.1 Safety status

Every applicable invariant remains one of:

| Status | Meaning | Can satisfy a safety gate? |
|---|---|---:|
| `pass` | The invariant was evaluated and no violation was found. | Yes |
| `fail` | A violation was observed. | No |
| `unsupported` | The invariant applies, but the provider cannot prove it. | No |
| `not_applicable` | The invariant does not apply to this case. | Only as non-applicable |

An aggregate safety gate is `pass` only when no applicable invariant is
`fail` or `unsupported`. A provider must not relabel fixture records through
provider-supplied metadata to hide a scope or lifecycle violation; the existing
fixture-backed checks at `evals/metrics.py:174-203` remain authoritative.

Case-level `passed` must have semantics consistent with the aggregate gate:
an applicable `unsupported` invariant cannot produce `passed: true`. The
implementation may add an explicit `unsupported_invariants` field or revise
the derived boolean, but it must preserve the existing invariant names and
make the distinction machine-readable. No consumer may infer safety success
from `passed` alone without checking the status fields.

### 4.2 Quality status

Quality is separate from safety. A report must expose one of:

| Status | Meaning | Promotion implication |
|---|---|---|
| `measured` | The requested quality metrics were computed on the declared cases. | May be used for a separately accepted quality gate. |
| `unavailable` | A required provider, metric, or measurement channel was unavailable. | Blocks quality promotion; never treated as zero or pass. |
| `not_applicable` | The report intentionally does not request that quality measure. | Cannot satisfy a gate that requires it. |
| `invalid` | Inputs or output failed deterministic validation. | Blocks the report. |

`context_precision` or another numeric field being present is not by itself
proof that the quality status is `measured`. `None`, unavailable feasibility,
or unavailable MRR must remain explicit. The current IG01-D
`SEMANTIC_UNAVAILABLE` result remains an honest diagnostic result and must not
be relabeled `MEASURED`.

W-09 does not introduce or change absolute retrieval thresholds. It only
requires that later packages cannot confuse a measured value with an
unavailable value.

### 4.3 Capability status

The report must preserve whether each required provider capability is:

- `supported` — the provider claims the capability and the evaluator exercised
  the corresponding invariant;
- `unsupported` — the capability was required but not available; or
- `not_applicable` — no case in the report requires it.

Capability status is evidence, not a waiver. `unsupported` remains a blocked
safety result when the invariant applies.

### 4.4 Evidence and overall gate status

Evidence reconciliation must expose one of:

- `verified` — all declared source and corpus identity values match a fresh
  recomputation;
- `stale` — the report is internally valid but no longer matches the current
  declared source or corpus;
- `tampered` — a persisted value, fingerprint, case set, or metric cannot be
  reconciled with the declared inputs;
- `invalid` — the report fails schema/privacy/structural validation; or
- `unavailable` — the source needed for reconciliation cannot be read.

An overall **measurement** result may be `complete` only when evidence is
`verified`, safety has no `fail` or `unsupported` applicable invariant, and all
requested cases were evaluated. It may carry `quality: unavailable` so long as
that fact is visible.

An overall **promotion** result is `blocked` whenever evidence is not
`verified`, any required safety invariant is `fail` or `unsupported`, quality
is `unavailable`/`invalid`, or the future V2-specific comparison contract is
not satisfied. W-09 does not authorize promotion; it only prevents a
measurement-only result from being mistaken for promotion evidence.

## 5. Source and tamper reconciliation

### 5.1 Canonical source identity

For every newly generated evidence report, bind:

- exact repository revision (`git_sha`);
- evaluator version;
- corpus/fixture version;
- ordered task IDs and task count;
- public/holdout split identity and split fingerprint;
- evaluation source fingerprint over the declared evaluator input paths;
- deterministic seed and noise configuration; and
- provider ID and role where a paired report is used.

The existing `baseline_snapshot._FINGERPRINT_PATHS` boundary remains the
allowlist for baseline-v3. Optional provider files must not silently change a
baseline that does not execute them.

### 5.2 Reconciliation behavior

Add or expose a read-only verification path that recomputes the declared
identity from an explicit repository root, fixture, and corpus root. It must
compare at least:

1. evaluator/schema version;
2. corpus version, fixture ID, suite and ordered task IDs;
3. public/holdout split and split fingerprint;
4. evaluation source fingerprint;
5. git revision when the root is a checkout; and
6. seed/noise/provider role parameters.

For deterministic baseline-v3, the normalized report comparison remains the
strongest check: rebuild the report, use the existing bounded float tolerance,
and compare every other scalar/list/object field exactly. The committed JSON
must not be edited to make a check pass.

For IG01-D, internal field agreement is necessary but insufficient. A report
whose SHA or fingerprint merely matches another field in the same JSON is not
`verified` until the declared root/corpus recomputation agrees. A caller may
inject a revision only in an explicitly marked test fixture; production
evidence must obtain it from the checked-out source.

On mismatch, fail closed with the bounded status and a content-free reason
code. Do not include prompts, transcripts, memory text, paths containing user
data, tokens, or credentials in the error or persisted report.

### 5.3 Privacy and report shape

The existing report contracts reject raw content keys in IG01-D. That rule
continues recursively. New status/provenance fields are bounded codes,
identifiers, hashes, counts, and finite numbers only. Unknown fields remain
rejected for versioned IG01-D reports. If a schema change is required, bump
the schema version and retain a read-only validator for the prior version;
never silently reinterpret an old report as new evidence.

## 6. Public and HOLDOUT boundaries

The following rules are non-negotiable:

1. Public `DEV+TEST` evidence never reads or uses HOLDOUT documents or labels.
2. Target derivation, provider selection, threshold decisions, and code tuning
   never inspect HOLDOUT.
3. A public report must state `split: ["dev", "test"]`, its task count, sorted
   task IDs, and split fingerprint.
4. The feasibility probe remains exactly 50 DEV cases, seed 17, noise 24, with
   `holdout_included: false` unless a separately versioned contract changes
   that boundary.
5. HOLDOUT is evaluated only by a dedicated explicit suite/command and its
   evidence is stored separately. A public command must not gain access to
   holdout labels through a path alias, broad glob, or default fallback.
6. Tests must make the boundary observable by blocking reads of holdout
   documents during public validation, as the current
   `test_public_baseline_validation_never_reads_holdout_documents` test does.

Changing a public result because a holdout answer was inconvenient is a hard
failure, even if the resulting aggregate score improves.

## 7. Backward compatibility

- `baseline-v1` and `baseline-v2` remain immutable historical artifacts. Their
  manifests and report hashes are checked as historical evidence and are never
  rewritten by W-09.
- Existing schema-version-1 generic reports remain readable when structurally
  valid, but a report without explicit reconciliation/status evidence is
  `legacy`/`unverified` and cannot satisfy a graduation or promotion claim.
- Existing callers that use `compare_evaluation_reports()` retain the current
  quality delta and invariant-change fields. New status fields may be additive;
  if a closed schema disallows that, use a new schema version and provide a
  deterministic migration/adapter for read-only comparison.
- Existing CLI exit behavior must remain backward compatible for a completed,
  safety-clean measurement. Its machine-readable output must additionally
  distinguish safety, quality, evidence, and promotion status; a single
  ambiguous `gate: pass` must not conceal `quality: unavailable` or
  `evidence: stale`.
- No committed baseline JSON is regenerated as part of the contract-only
  change. Any generated evidence in implementation must be bound to the exact
  implementation SHA and reported separately.

## 8. Focused test and evidence plan

The implementation package must add or update tests without changing corpus
labels or holdout files.

### 8.1 Case and gate semantics

- An applicable `unsupported` invariant produces a non-passing case/gate.
- `not_applicable` does not create a false failure, but cannot satisfy an
  invariant that the task requires.
- A `fail` invariant is never hidden by a quality improvement.
- A safety-clean result with `quality: unavailable` is visibly measurement-only
  and cannot report promotion-ready.
- A select-everything provider has measurable precision/noise/token impact;
  recall alone cannot produce a quality pass.

### 8.2 Reconciliation and tamper tests

For a fixed public fixture and corpus, generate an evidence report and verify
that:

- unchanged source, corpus, evaluator, task IDs, seed, and noise reconcile;
- changed git SHA, evaluator fingerprint, corpus fingerprint, task set, seed,
  noise, or provider role returns `stale`/`tampered`/`invalid` and never green;
- a structurally valid report with self-consistent but false source metadata is
  not accepted as verified;
- changed numeric metrics or case rows are detected by deterministic baseline
  comparison;
- baseline-v3 float round-off remains accepted only under its existing bounded
  tolerance, while non-float fields still require exact equality;
- historical baseline manifests remain byte/hash protected.

### 8.3 Privacy and split tests

- raw prompt, transcript, memory content, secret, token, and credential keys
  remain rejected recursively;
- validation errors contain only bounded codes and no untrusted content;
- public validation never opens HOLDOUT documents;
- public fingerprints and task counts cannot be changed by a HOLDOUT-only edit;
- a dedicated HOLDOUT run reports its split explicitly and cannot be used as a
  public target derivation input.

### 8.4 Regression evidence

Run at minimum:

```text
.venv\Scripts\python.exe -m pytest tests/test_evaluation_metrics.py tests/test_evaluation_reporting.py tests/test_evaluation_runner.py tests/test_evaluation_baseline_snapshot.py tests/test_ig01d_baseline.py -q
.venv\Scripts\python.exe -m pytest tests -q
.venv\Scripts\python.exe -m flake8 --select E9,F63,F7,F82 evals tests
.venv\Scripts\python.exe -m compileall -q evals
git diff --check
```

The exact commands, revision, result counts, warning count, corpus split
fingerprints, and generated report hashes belong in the package report.

## 9. Exit gate

W-09 cannot close until all of these are true:

- `unsupported` cannot serialize or aggregate as a passing applicable case;
- safety, quality, capability, evidence, measurement, and promotion statuses
  are distinct and machine-readable;
- source/corpus/revision reconciliation detects self-consistent stale or
  tampered reports;
- public/HOLDOUT boundaries are tested by observable read guards;
- baseline-v3, baseline-v1, and baseline-v2 invariants remain intact;
- no quality threshold, corpus label, retrieval algorithm, or V2/Phase 20
  boundary changed;
- report privacy and bounded error behavior pass;
- focused tests, full suite, critical static checks, compile/import checks, and
  diff checks pass at one exact revision;
- a package report lists before/after evidence, known limitations, and open
  failures; and
- an independent read-only reviewer returns exactly `SHIP`.

`FIX-FIRST` applies to any unbound source, hidden unsupported capability,
holdout read, privacy leak, or regression. `RETHINK` applies if the proposed
schema cannot preserve historical reports without weakening evidence meaning.
The implementation author must not issue the final verdict.

## 10. Package report template

```text
PACKAGE: W-09 — Evaluation Evidence Integrity & Gate Semantics
REVISION: <exact implementation SHA>
OBJECTIVE: <one sentence>
FILES CHANGED: <evaluation/test/report files only>
ROOT CAUSES ADDRESSED: <evidence and gate findings>
TESTS ADDED: <names and purpose>
TESTS EXECUTED: <exact commands and results>
QUALITY METRICS BEFORE: <measurement only; no goalpost changes>
QUALITY METRICS AFTER: <measurement/status deltas>
SAFETY METRICS: <all invariant states and unsupported counts>
EVIDENCE RECONCILIATION: <source/corpus/revision status and hashes>
HOLDOUT BOUNDARY: <public and dedicated holdout evidence>
KNOWN LIMITATIONS: <unavailable providers or deferred gates>
OPEN FAILURES: <none or exact bounded failures>
INDEPENDENT REVIEW: <SHIP / FIX-FIRST / RETHINK, separate reviewer>
SCORE BEFORE: <evaluation-evidence score>
SCORE AFTER: <evaluation-evidence score; do not inflate retrieval quality>
VERDICT: REVIEW PENDING
```

**Contract status: REVIEW PENDING — implementation has not started.**
