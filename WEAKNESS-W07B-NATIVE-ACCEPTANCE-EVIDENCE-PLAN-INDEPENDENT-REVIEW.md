# W-07B Native Acceptance Evidence Plan — Independent Review

**Reviewer:** `/root/w10_exact_review` (read-only)

**Verdict:** `SHIP` (plan only)

The revised plan closes the earlier ambiguity without changing production
code. It requires both real Claude and Codex executable paths to be
`VERIFIED`; an unavailable environment leaves W-07B `FIX-FIRST` and cannot be
used as a release exception. The plan pins the current exact baseline and
dependency graph, defines deterministic named kill barriers for worker and
service processes, and requires the complete client/event/cold/warm latency
matrix with explicit percentile calculation.

The canonical-effect requirement is deterministic: a controlled capture input
must verify an opaque canonical effect, or an explicit terminal `zero_effect`
receipt with an unchanged canonical revision. Unrelated green CI is not
accepted as native evidence; matching remote jobs are recorded by workflow,
run ID, head SHA and conclusion, otherwise `NOT APPLICABLE` remains visible.

Privacy, live-vault isolation, cleanup, canonical authority boundaries,
Phase 20 `FROZEN / LOCKED` and V2 `SHADOW` constraints are all preserved.
This verdict accepts the evidence plan only; W-07B runtime implementation
remains `FIX-FIRST / NOT ACCEPTED` until the evidence gates and a separate
implementation review pass.
