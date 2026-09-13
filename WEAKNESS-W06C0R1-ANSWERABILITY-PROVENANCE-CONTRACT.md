# W-06C0R1 — Retrieval Corpus Answerability and Provenance Contract

**Status:** CONTRACT REVIEW PENDING  
**Program:** Engineering Weak-Point Improvement Goal  
**Package type:** evaluation-only contract successor to W-06C0  
**Phase 20:** FROZEN / LOCKED  
**V2 runtime:** SHADOW  
**Predecessor:** W-06C0 contract `SHIP` at `fa5b920`; implementation/evidence
review `FIX-FIRST` at `60f8e08`  

## 1. Purpose

W-06C0 corrected the benchmark vocabulary and provider matrix, but its final
contract still left two measurement-integrity choices open:

1. the exact canonical hash inputs and framing for the manifest/source evidence;
2. a mandatory, machine-checkable proof that all provider slots used the same
   candidate snapshot and ordering.

W-06C0R1 defines a new, independently reviewed `corpus-v4` and its provenance
boundary. It is a documentation and evaluation package only. It does not tune
retrieval, change production behavior, or authorize a successor runtime.

`corpus-v3`, its manifest, labels, reports, and source/evidence history remain
immutable. No W-06C0R1 implementation may rewrite, migrate, or silently reuse a
v3 label.

## 2. Scope and explicit exclusions

### 2.1 Included

The package may add only:

- `evals/corpus-v4/` public synthetic or sanitized retrieval cases, manifest,
  and attestation metadata;
- `evals/w06c0r1/` evaluation-only loader, provenance, attestation, and report
  validation code;
- `tests/test_w06c0r1_*.py` focused evaluator tests;
- `WEAKNESS-W06C0R1-PACKAGE-REPORT.md` evidence.

The evaluator must support explicit selection of `corpus-v4` and the
`w06c0r1-v1` evaluator version. It must not change the default behavior of
W-09A, IG01-C, W-06C0, or any production caller.

### 2.2 Excluded

The following remain byte-stable and outside this package:

- `evals/corpus-v2/**`, `evals/corpus-v3/**`, `evals/w06c0/**`, `evals/w09a/**`,
  `evals/ig01c/**`, and their existing reports;
- `brain_eleven/**`, `scripts/**`, `context_compiler_v2/**`, `authority/**`,
  `context_router/**`, `.claude/**`, MemoryStore, StateStore, ProjectRegistry,
  capture, extraction, lifecycle, or canonical writers;
- embedding downloads, API-key handling, provider promotion, cache migration,
  V2 promotion, SessionStart changes, Phase 20 work, and ranking tuning;
- private real prompts, transcripts, memory contents, credentials, filesystem
  paths, or project identifiers in the repository or reports.

No W-06C1 runtime contract may be drafted from W-06C0R1 results until this
package independently returns `SHIP`.

## 3. Corpus-v4 contract

### 3.1 Fixed layout and counts

The exact public path is:

```text
evals/corpus-v4/
  manifest.json
  dev/*.json
  test/*.json
  holdout/*.json
  attestations/*.json
```

The manifest is schema version `1`, corpus version `4`, and must declare these
exact total counts:

```json
{
  "schema_version": 1,
  "corpus_version": 4,
  "suite_counts": {"dev": 60, "test": 60, "holdout": 30},
  "minimum_answerable_counts": {"dev": 45, "test": 45, "holdout": 22},
  "answerability_version": "w06c0r1-v1",
  "provenance_version": "w06c0r1-provenance-v1"
}
```

Every split must contain exactly its declared number of case files. Every split
must contain at least its declared number of `answerable` cases. Cases that do
not meet the answerability rule remain visible only as `unanswerable` or
`review_required`; they cannot be relabeled to satisfy the minimum.

Each DEV, TEST, and HOLDOUT split must contain all of the following answerable
phenomena, with at least one case per phenomenon: exact relevant memory,
paraphrase, old critical decision, current state or blocker, related lesson,
recent irrelevant distractor, same-keyword wrong meaning, superseded or
resolved distractor, and cross-project distractor. A case may cover multiple
phenomena, but the manifest must record the category list and counts.

The corpus contains only public synthetic or sanitized cases. A private
realistic corpus, if used for local feasibility probes, is local-only, is not
hashed into public case content, and is never copied into reports.

### 3.2 Case schema and answerability

Each case retains the retrieval task, candidate snapshot description, required,
acceptable/useful, forbidden, lifecycle, project, and safety fields. It adds:

```json
"answerability": {
  "status": "answerable",
  "reason": "query_and_candidate_metadata_support_target",
  "review_version": "w06c0r1-v1",
  "case_payload_hash": "sha256:<64 lowercase hex characters>",
  "attestation_hash": "sha256:<64 lowercase hex characters>"
}
```

Allowed statuses are exactly `answerable`, `unanswerable`, and
`review_required`. Allowed reasons are exactly:

- `query_and_candidate_metadata_support_target`;
- `query_lacks_target_discriminator`;
- `gold_label_depends_on_hidden_fixture_metadata`;
- `candidate_snapshot_incomplete`;
- `annotation_disagreement`;
- `privacy_or_schema_review`.

`unanswerable` and `review_required` cases remain in their original split,
appear in excluded counts, run safety checks, and never enter quality
aggregates. Unknown status or reason values fail closed. No hidden scenario
number, fixture ID, gold label, or expected memory ID may be added to provider
inputs to make a case answerable.

### 3.3 Two-labeler attestation

Every case has one matching file at
`evals/corpus-v4/attestations/<case_id>.json`. The attestation is content-free
and has this exact logical shape:

```json
{
  "schema_version": 1,
  "corpus_version": 4,
  "case_id": "<public-case-id>",
  "split": "dev",
  "review_version": "w06c0r1-v1",
  "case_payload_hash": "sha256:<64 lowercase hex characters>",
  "labelers": [
    {"id_hash": "sha256:<64 lowercase hex characters>", "status": "answerable", "reason": "..."},
    {"id_hash": "sha256:<64 lowercase hex characters>", "status": "answerable", "reason": "..."}
  ],
  "agreement": true,
  "attestation_hash": "sha256:<64 lowercase hex characters>"
}
```

The two `id_hash` values must differ. Raw labeler identity is never stored.
Each public case is independently labeled by both labelers; a disagreement
must produce `agreement=false` and `status=review_required` in the case. A
single implementer cannot resolve a disagreement by changing either label or
its reason. The attestation must bind the final case payload hash, split,
corpus version, review version, both decisions, and agreement bit.

HOLDOUT labels are created and attested before any provider or evaluator tuning.
The HOLDOUT label files and attestations are sealed after that review. DEV/TEST
loader code must not open, import, or hash HOLDOUT labels; only the explicit
final-probe command may unlock them after DEV/TEST evidence is frozen.

## 4. Canonical provenance and hash formula

All hashes in this package use lowercase `sha256:` followed by exactly 64
hexadecimal characters. Before hashing, text values are Unicode NFC normalized,
line endings are converted to LF, and JSON is encoded as UTF-8 using:

```text
json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':'))
```

No whitespace, timestamp, filesystem path, random seed, or generated report
field may enter a case or attestation payload hash unless named below.

### 4.1 Case payload hash

`case_payload_hash` is the SHA-256 of the canonical case object after removing
only `answerability.case_payload_hash` and `answerability.attestation_hash`.
The corpus version, split, case ID, task, candidates, labels, lifecycle and
safety fields therefore remain bound to the hash.

### 4.2 Attestation hash

`attestation_hash` is the SHA-256 of the canonical attestation object after
removing only `attestation_hash`. It binds:

```text
schema_version, corpus_version, case_id, split, review_version,
case_payload_hash, ordered labeler records, agreement
```

The case's `answerability.attestation_hash` must equal its matching
attestation file's hash. The case's `answerability.case_payload_hash` must equal
the recomputed case hash. Any mismatch, missing file, duplicate case, extra
attestation, symlink, or path traversal fails closed.

### 4.3 Manifest and split fingerprints

The manifest must include one SHA-256 for every case and attestation file using
the normalized bytes above. It must also include:

- `manifest_hash`: SHA-256 of the canonical manifest with only `manifest_hash`
  removed;
- one `split_fingerprint` per split;
- `source_fingerprint`;
- `case_count`, `answerable_count`, `unanswerable_count`, and
  `review_required_count` per split.

For a split, sort relative POSIX paths and hash length-prefixed frames:

```text
u64_be(len(path_utf8)) || path_utf8 || u64_be(len(normalized_file_bytes)) || normalized_file_bytes
```

The split fingerprint is the SHA-256 of the concatenated frames. The manifest
hash uses the same canonical JSON rules and does not include itself.

### 4.4 Provider snapshot and task-set fingerprints

The following formulas are normative and use the framing from §4.3. Every
string is NFC-normalized and LF-normalized before UTF-8 encoding.

- `candidate_content_fingerprint` is the SHA-256 of frames for the sorted
  candidate rows. Each row is the canonical JSON object
  `{"candidate_id": ..., "type": ..., "status": ..., "scope": ...,` 
  `"project_id": ..., "content": ...}` sorted by `candidate_id`; each frame
  is `u64_be(len(row_utf8)) || row_utf8`.
- `candidate_order_fingerprint` is the SHA-256 of
  `u64_be(source_memory_revision) || u64_be(candidate_count)` followed by one
  `u64_be(len(candidate_id_utf8)) || candidate_id_utf8` frame for each ID in
  the exact order supplied to the provider.
- `task_set_fingerprint` is the SHA-256 of
  `u64_be(len(split_utf8)) || split_utf8 || u64_be(case_count)` followed by
  length-prefixed public case IDs in their exact corpus order. It is report
  evidence only; it is never passed to provider code.

All three values use the `sha256:<64 lowercase hex>` form. Reordering
candidates changes the order fingerprint, changing any normalized candidate
field changes the content fingerprint, changing the source revision changes
the order fingerprint, and changing split or ordered case IDs changes the
task-set fingerprint. The implementation must test each mutation.

### 4.5 Source fingerprint

The exact W-06C0R1 source allowlist is the sorted set of tracked files matching:

```text
evals/w06c0r1/**/*.py
tests/test_w06c0r1_*.py
```

The source fingerprint uses the same length-prefixed frame algorithm as split
fingerprints, with relative POSIX path and normalized file bytes. Missing,
untracked, symlinked, or out-of-root files fail closed. The fingerprint is
computed after the implementation diff is complete and is copied into every
provider report and package report. A report with a source fingerprint that
does not match the exact checkout is invalid.

## 5. Evaluator version and provider input identity

The evaluator must require an explicit `--corpus-version corpus-v4` or an
equivalent typed API argument. No implicit “latest” corpus selection is
allowed. The report must include:

```text
evaluator_version = w06c0r1-v1
corpus_version = 4
split = dev|test|holdout
manifest_hash
split_fingerprint
source_fingerprint
```

All provider slots receive the same generated vault, task set, scope policy,
and candidate snapshot. Before invoking a provider, the harness computes:

- `candidate_content_fingerprint`: sorted `(candidate_id, normalized_content)`
  frames;
- `candidate_order_fingerprint`: ordered candidate IDs as supplied;
- `source_memory_revision`;
- a task-set fingerprint binding ordered case IDs and split.

These four values are required in every provider row. Any mismatch between
provider rows is a hard parity failure, even when candidate counts match.
Provider code receives no answerability labels, attestation files, public case
IDs, expected IDs, or hidden fixture metadata. The harness creates an opaque
per-run `task_handle` (`task-000001`, `task-000002`, ...) and passes that value
through the existing task-id field only so the normalized provider interface
can correlate a response. The mapping from `task_handle` to public case ID is
held outside provider input and is applied only after the provider returns.
Providers must treat the handle as opaque and may not use it to infer labels.

Provider output remains content-free and must include requested slot, actual
provider ID, model/schema identity, availability, run status, bounded error
code, latency, candidate count, selected count, the four input fingerprints,
and selected candidate hashes. Fallback identity is explicit; unavailable
providers are `NOT_MEASURED`, never a pass.

## 6. Privacy and holdout rules

- Reports and attestations contain no raw prompt, memory content, transcript,
  token, credential, filesystem path, private project ID, or API response.
- Candidate IDs in reports are hashes unless the existing public synthetic
  evaluation contract explicitly permits the public case ID boundary.
- External providers are opt-in probes only; credentials are read from the
  process environment and never serialized.
- Provider caches, model files, generated vaults, and temporary reports exist
  only below an isolated temporary directory and are removed after the probe.
- DEV/TEST runs must fail if they attempt to read HOLDOUT labels or attestations.
- `evals/corpus-v4/holdout/seal.json` is the machine-checkable seal. It binds
  `corpus_version`, the manifest/split/attestation fingerprints, the exact
  DEV/TEST evidence revision and report hashes, and `state="SEALED"`.
  DEV/TEST code must reject a missing seal, a changed seal, or any unlock
  marker. Only the explicit final-probe command may consume a one-time
  unlock token whose hash is recorded in its content-free evidence together
  with the seal hash, command hash, and final report hash. The final probe
  cannot rewrite the seal, corpus, production files, or provider cache.

The seal file has this exact content-free shape (the final field is excluded
from `seal_hash`):

```json
{
  "schema_version": 1,
  "corpus_version": 4,
  "split": "holdout",
  "state": "SEALED",
  "sealed_at_revision": "<40-hex-git-sha>",
  "dev_test_evidence_revision": "<40-hex-git-sha>",
  "manifest_hash": "sha256:<64 lowercase hex characters>",
  "split_fingerprint": "sha256:<64 lowercase hex characters>",
  "attestation_fingerprint": "sha256:<64 lowercase hex characters>",
  "dev_test_report_hashes": ["sha256:<64 lowercase hex characters>"],
  "seal_hash": "sha256:<64 lowercase hex characters>"
}
```

The final probe verifies that `dev_test_evidence_revision` is an ancestor of
`sealed_at_revision`, that all fingerprints match the immutable corpus, and
that the supplied one-time unlock token hashes to a token recorded only in
the final evidence. DEV/TEST commands reject any state other than
`SEALED` and never consume the token. A second final-probe invocation with
the same token fails closed.

## 7. Exact implementation allowlist

The package may change only:

```text
evals/corpus-v4/**
evals/w06c0r1/**
tests/test_w06c0r1_*.py
WEAKNESS-W06C0R1-PACKAGE-REPORT.md
```

Every other tracked path is forbidden, including `corpus-v2`, `corpus-v3`,
`evals/w06c0`, `evals/w09a`, `evals/ig01c`, all runtime/retrieval/canonical
packages, `.claude`, and existing reports. A machine-checkable allowlist must
fail before any package report is accepted and must record an exact before/after
zero-diff assertion for forbidden paths.

## 8. Tests and exit gates

The focused evaluator tests must cover:

1. canonical JSON normalization, case/attestation hashes, manifest hash, split
   fingerprints, source fingerprint and tamper detection;
2. exactly two distinct labeler hashes, disagreement handling, unknown status or
   reason rejection, missing/extra attestation rejection and case-count minima;
3. explicit corpus/evaluator version selection and v3/v2 immutability;
4. DEV/TEST inability to read HOLDOUT labels, seal/unlock chronology and
   final-probe unlock only after frozen DEV/TEST evidence, and no
   private-content output;
5. identical candidate content/order/revision/task fingerprints across all
   provider slots, mismatch hard failure, fallback identity and unavailable
   `NOT_MEASURED` behavior;
6. perfect selection, select-all, select-none, answerability exclusion,
   duplicate IDs, all required K values, and every hard safety gate;
7. exact allowlist enforcement, zero forbidden diff, isolated temporary writes,
   critical flake8 (`E9,F63,F7,F82`), compile/import sanity, full regression,
   and `git diff --check`.

W-06C0R1 is `SHIP` only when all of these are true:

- corpus-v3 and every predecessor report are byte-stable;
- corpus-v4 counts, answerable minima, category coverage, attestations and all
  hashes validate;
- source, manifest, split, candidate, order, revision and task fingerprints are
  reproducible and provider-identical;
- HOLDOUT sealing and final-probe evidence pass;
- reports are privacy-safe and all safety gates remain zero;
- exact allowlist and full verification pass;
- an independent read-only reviewer returns exactly `SHIP`.

Any provenance mismatch, holdout access before final probe, scope violation,
privacy leak, or unexplained provider parity failure is `FIX-FIRST`. A corpus
whose answerable minimum cannot be met without hidden labels is `RETHINK`.

## 9. Package report template

```text
PACKAGE: W-06C0R1
REVISION: <exact implementation/review SHA>
OBJECTIVE: <bounded corpus-v4 answerability/provenance correction>
FILES CHANGED: <exact allowlisted paths>
ROOT CAUSES ADDRESSED: <fingerprint ambiguity, candidate snapshot parity>
TESTS ADDED: <focused tests>
TESTS EXECUTED: <commands and exact results>
QUALITY METRICS BEFORE: <frozen v3/W-06C0 evidence>
QUALITY METRICS AFTER: <v4 answerable DEV/TEST/HOLDOUT evidence>
SAFETY METRICS: <all hard gates and privacy checks>
PROVENANCE EVIDENCE: <manifest/source/case/attestation/snapshot hashes>
HOLDOUT EVIDENCE: <seal and final-probe evidence>
KNOWN LIMITATIONS: <provider availability and corpus limits>
OPEN FAILURES: <none or exact failures>
INDEPENDENT REVIEW: <SHIP / FIX-FIRST / RETHINK, exact review SHA>
SCORE BEFORE: <evaluation/retrieval score>
SCORE AFTER: <evidence-backed score, no unsupported increase>
VERDICT: <SHIP / FIX-FIRST / RETHINK>
```

**Contract status: REVIEW PENDING — implementation has not started.**
