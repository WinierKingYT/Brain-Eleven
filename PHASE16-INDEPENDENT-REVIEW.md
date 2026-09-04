# Phase 16 — Independent Graduation Review

**Status:** Required after CI evidence; no verdict is recorded in this file.

## Reviewer independence

The reviewer must not be the person or agent that implemented the Phase 16
changes. This is a read-only audit of a fixed revision, not a second
implementation pass. It must cite the reviewed commit SHA and the matching
`phase16-task-state-evidence` CI artifact.

## Required evidence

- Green unit, integration, coverage and security jobs for the reviewed SHA.
- Green `Phase 16 task/state smoke suite` and public suite.
- Green `phase16-task-state-evidence` artifact generated from JUnit and the
  full public-plus-holdout evaluator report.
- No unreviewed local or private state corpus included in the revision.

## Review questions

1. Are `MemoryStore`, `ProjectRegistry`, `StateStore`, and runtime
   `TaskEnvelope` still separate authorities?
2. Can task analysis create, rename, relocate, or archive a project?
3. Can corrupt, missing, unavailable, or stale state become an implicit empty
   success or be injected into SessionStart?
4. Does every canonical state mutation reload under lock, enforce the expected
   per-project revision, write atomically, and record trusted provenance?
5. Do 10 concurrent writers preserve all successful mutations without a lost
   update? Are stale revisions reported rather than overwritten?
6. Can an `ai_proposed` source, arbitrary JSON patch, secret, dangling memory,
   or different-project memory become canonical state without an explicit
   diagnostic?
7. Does default state resolution return only the requested project, including
   when a similarly named project has active blockers?
8. Does a bootstrap reject a changed state revision or state status as stale?
9. Does backup/restore preserve canonical state identities while still
   rebuilding graph and bootstrap projections from authoritative data?
10. Are project status claims bounded by runtime evidence rather than stronger
    than the available CI result?

## Verdict format

Return exactly one of:

- **SHIP** — all graduation invariants have revision-bound evidence.
- **FIX-FIRST** — an implementation or evidence blocker is identified with a
  reproducible path.
- **RETHINK** — the authority boundaries or Phase 16 scope are not sound.

The reviewer records the verdict, commit SHA, CI artifact URL, findings, and
any follow-up work in a separate review result. Do not edit this checklist to
represent a verdict.
