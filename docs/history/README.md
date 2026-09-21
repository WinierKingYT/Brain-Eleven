# docs/history — archived documentation

**Class: HISTORICAL.** These files are retained for provenance only. Do not infer
current behavior, CI, deployment, runtime wiring or release state from anything
here. For current state read the root `PROJECT-STATUS.md`, the active IG package
contract, `DOCUMENTATION-AUTHORITY.md` and `RUNTIME-DATAFLOW.md`.

Archived content and verdicts are never rewritten. When a file moves here, every
reference to it from an active document is updated in the same change. A path
written inside an archived file may still point at the pre-archive layout (bare
`FILENAME.md` at the repo root); it is kept as provenance and must not be
followed as a link to current content.

On 2026-09-18, six root-level snapshots were moved here with `git mv` to
reduce active-root noise while preserving history: two superseded W-24 contract
re-reviews, two superseded W-25 contract re-reviews, the completed vault
hygiene report, and the completed IG-07 Slice 2E E1 baseline contract. Their
final/current successors remain at the repository root where the authority
registry or package status points to them.

## Contents

A second bounded pass on 2026-09-18 moved 30 unregistered, unreferenced W-01–W-18
and TSC-03 contract/review records into `weakness/`. They remain available for
provenance; current authority-registered contracts, package reports and final
reviews stay at the root.

| Group | Files |
|---|---|
| Phase plans / summaries / roadmaps | `PHASE5-SUMMARY`, `PHASE6-PLAN`, `PHASE6-SUMMARY`, `PHASE7-PLAN`, `PHASE7-STATUS`, `PHASE10-DEEP-DIVE`, `PHASE11-KICKSTART`, `PHASE11-PLANNING`, `PHASE13-PLAN`, `PHASES-8-9-10-ROADMAP` |
| Phase 16–19 component contracts | `PHASE16-TASK-STATE-CONTRACT`, `PHASE17-TASK-AWARE-CONTEXT-ROUTER-CONTRACT`, `PHASE18-AUTHORITY-CONFLICT-CONTRACT`, `PHASE19-CONTEXT-COMPILER-V2-CONTRACT` |
| Phase 16–19 independent reviews | `PHASE16-INDEPENDENT-REVIEW`, `PHASE17-INDEPENDENT-REVIEW`, `PHASE18-INDEPENDENT-REVIEW`, `PHASE19-INDEPENDENT-REVIEW` |
| PRE-program records | `PRE13-TECHNICAL-CLOSURE`, `PRE20-12-REPOSITORY-CONSOLIDATION`, `PRE-PHASE20-CORE-INTELLIGENCE-HARDENING-CONTRACT` |
| Context Engine Foundation V1 | `CONTEXT-ENGINE-FOUNDATION-V1`, `CONTEXT-ENGINE-FOUNDATION-V1-INDEPENDENT-REVIEW` |
| Historical operational guides | `TESTING`, `TESTING-FRAMEWORK`, `DEPLOYMENT-STACK`, `INTEGRATION-CHECKLIST`, `ORCHESTRATION-STATUS`, `PARALLEL-ORCHESTRATION` |
| Superseded review snapshots, baseline contract and vault audit | `WEAKNESS-W24-MEMORY-TRUTH-SAFETY-INDEPENDENT-REVIEW-02`, `WEAKNESS-W24-MEMORY-TRUTH-SAFETY-INDEPENDENT-REVIEW-03`, `WEAKNESS-W25-HTTP-SCOPE-AUTHORIZATION-CONTRACT-INDEPENDENT-REVIEW`, `WEAKNESS-W25-HTTP-SCOPE-AUTHORIZATION-CONTRACT-INDEPENDENT-REVIEW-02`, `IG07-SLICE2E-E1-CONTRACT`, `VAULT-HYGIENE-REPORT` |
| Historical weakness contracts/reviews | `weakness/` — 30 W-01–W-18 and TSC-03 records moved after authority and reference checks |
| Closed package reports | `reports/` — completed package reports retained as revision-bound evidence |
| Independent reviews | `reviews/` — completed independent review records retained with their original content |
| Generated investigation evidence | `evidence/` — historical Codex/D0/R0 result records; not current authority |
| Documentation cleanup records | `DOCUMENTATION-CLEANUP-2026-09-18` |
| Documentation cleanup records | `DOCUMENTATION-CLEANUP-2026-09-22` |
| Misc | `hamle6_notes_content.txt` |
