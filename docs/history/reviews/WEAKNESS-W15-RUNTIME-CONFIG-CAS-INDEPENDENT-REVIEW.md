# W-15 Runtime Configuration CAS Independent Review

**Verdict:** SHIP  
**Reviewed package head:** `7fd9d5a72d3995723c4f13f6fd07b541959ba30a`  
**Implementation:** `72614fe`  
**Evidence/report:** `79eb52a11953c64dd8a8ffcf669787465709ccbf`

## Scope checked

The review inspected the contract, storage/install diff, focused tests,
existing runtime tests, and repository boundaries. Changes are bounded to
`brain_eleven/runtime/storage.py`, the installer’s runtime-config mutation
call, focused W-15 tests, and evidence documents. MemoryStore, StateStore,
retrieval, V2, and Phase 20 were unchanged.

## Findings

- `set_mode()` and `set_human_approval()` validate a snapshot, then commit
  under the existing `config.json` sidecar lock with deterministic
  fingerprint comparison.
- A stale snapshot raises `RuntimeConfigConflict` before any config write.
- CANARY/ACTIVE validation remains outside the commit lock; an intervening
  `OFF` cannot be overwritten by the delayed result.
- Installer project-ID/mode updates use the same locked current-config helper,
  preserving concurrent approval/mode fields.
- Existing atomic temp-file, flush, fsync and replace behavior remains the
  sole config writer; CLI `ValueError` compatibility is preserved.
- Phase 20 remains `FROZEN / LOCKED`; V2 remains `SHADOW`.

## Independent verification

- W-15 plus IG00/B1/PRE13/W06B/IG02 focused suite: **119 passed**, 2 existing
  FastAPI/AnyIO warnings.
- Critical flake8 (`E9,F63,F7,F82`): **PASS**.
- `compileall`: **PASS**.
- `git diff --check`: **PASS**.
- Same-field stale conflict, both cross-field races, stale CANARY→OFF,
  installer/approval race, lock failure/no mutation, and field preservation:
  **PASS**.

## Non-blocking note

The focused additions do not separately invoke an ACTIVE-vs-OFF race or a CLI
subprocess parity case. The ACTIVE path shares the reviewed `_commit()` guard,
and existing runtime tests cover CLI/schema behavior. This is follow-up
coverage only and is not a ship blocker.

## Conclusion

No P0, P1, or P2 blocking findings. W-15 is independently **SHIP** at the
exact package head.
