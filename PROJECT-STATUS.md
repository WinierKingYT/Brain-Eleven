# Brain-Eleven v3 — Current Project Status

**Last updated:** 2026-09-03
**Current milestone:** Phase 14G Memory Foundation Graduation — runtime evidence and documentation closure complete; final audit re-check pending.

## Status vocabulary

| Status | Meaning |
|---|---|
| **VERIFIED** | A bounded claim has reproducible automated evidence or a revision-bound CI result. |
| **PARTIALLY VERIFIED** | The implementation is present, but a required environment or operational check is still absent. |
| **NOT VERIFIED** | No adequate evidence exists; this is not a claim of failure. |
| **HISTORICAL** | A past implementation or validation record; it does not describe the current head. |

“Implemented” and “verified” are deliberately different: an implementation is
only **VERIFIED** when its stated evidence can be rerun or inspected.

## Product boundary

Brain-Eleven is a local, privacy-first second-brain system. Canonical memory
remains in the vault; API, hooks, context compiler, knowledge graph and search
layers consume that same validated store rather than creating parallel write
paths.

## Current evidence-backed state

| Area | Status | Evidence boundary |
|---|---|---|
| Canonical memory authority | **VERIFIED** | `MemoryStore` is the revisioned, locked and atomic canonical write boundary; malformed input and write failures are tested fail-closed. |
| Cross-project isolation | **VERIFIED** | Default retrieval admits global + current-project memory only; conflict, dedup, graph and context tests cover wrong-project exclusion. |
| Derived-state safety | **VERIFIED** | Graph and bootstrap are revisioned projections. Missing/corrupt projections rebuild; stale or scope-mismatched bootstrap is rejected. |
| Concurrent writers | **VERIFIED** | Graduation tests cover 10 simultaneous writers, 20 reopened transactions, stale CAS, lock timeout and writer crash recovery with zero lost updates. |
| Backup and restore | **VERIFIED** | A manifest/checksum ZIP restores into a blank vault, preserves canonical IDs/revision/lifecycle, then rebuilds graph and context. Corrupt or overwrite targets are refused. |
| CI and release topology | **VERIFIED** | Unit, integration, coverage, Bandit, secrets, dependency and image-security gates precede the validated-image publish workflow. CI evidence is revision-bound; inspect the matching Actions run for a particular head. |
| Global `/remember` installer | **PARTIALLY VERIFIED** | The installer and portability tests are versioned; installation into each user’s global Claude configuration remains a local operational action. |
| Live Docker Compose deployment (local Docker Desktop) | **VERIFIED** | On 2026-09-02, `app`, `postgres`, and `redis` became healthy; `127.0.0.1:8000/health` returned 200; the API port was unreachable through a non-loopback IPv4 address. The API key was unset, so its optional auth-gate branch was not applicable. |
| Public deployment and daily-use telemetry | **NOT VERIFIED** | Outside the local-first memory-foundation graduation boundary. |

## Runtime graduation evidence

The manifest is generated, never edited by hand:

```powershell
python scripts/graduation_evidence.py run --output .phase-evidence/phase14-graduation.json
```

It records the exact test count, coverage, runtime, invariant outcomes,
wrong-project leakage and lost-update metrics from JUnit/Cobertura output.
The artifact is intentionally ignored by Git. In GitHub Actions, the same
manifest is produced only after all security hard gates pass and is uploaded as
the `phase14-graduation-evidence` artifact. The validation run for the Phase
14G implementation revision `004627e87ae007ad6e1a30e493b460cce49542f1`
completed successfully and retains that artifact: [GitHub Actions run 33721296500](https://github.com/WinierKingYT/Brain-Eleven/actions/runs/33721296500).
An earlier local regeneration at historical commit
`9bfdb0cad928884a5ba3a590f27fd58fe9dd9dcf` produced `PASS` with 341/341 tests,
83.11% coverage, zero wrong-project leakage, and zero lost updates. A manifest
itself does not claim live deployment verification; that separate, bounded
runtime check is recorded in the table above.

## Operational guidance

- Keep proactive capture opt-in. Register a project before enabling it and use
  project scope for project decisions; reserve global scope for intentional
  cross-project facts.
- Treat hook failures as degraded convenience behavior, never as permission to
  bypass validation or write canonical memory directly.
- Retain migration backups until normal use has been observed and a verified
  backup/restore drill has completed for the intended vault.
- The independent Phase 14G re-check returned `FIX-FIRST` on 2026-09-03 solely
  because this document cited a historical commit as current evidence. The
  revision-bound record above corrects that provenance; obtain a final
  independent verdict before declaring the foundation frozen.

## Historical planning documents

Older phase plans are **HISTORICAL** execution records. They may contain
superseded assumptions; use this file and revision-bound evidence artifacts for
the current state.
