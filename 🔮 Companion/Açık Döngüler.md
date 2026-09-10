---
type: memory
title: Open Loops - Unresolved Work
category: Working Memory
status: active
created: 2026-08-28
---

# Open Loops (Unresolved)

## Current open work (2026-09-10)

These are the unresolved items supported by the current repository state and this session:

- [ ] **Ahmet confirmation required:** verify whether the six old GitHub branches were deleted; this cannot be established from the local checkout alone.
- [ ] Remote exact-head CI and live native-client trust remain open follow-ups for IG-04 B1 and B2.
- [ ] The next IG-04 subpackage has not been selected yet.
- [ ] IG-04 B2 independent read-only review is still pending; the implementation is not self-declared as accepted.

## Historical / abandoned plans

> The Hamle 7 Phase 1/2/3 and mem0 blocks below are historical and abandoned. They are conceptually archived under `docs/history/`; the original text is retained here for traceability and is not active work.


**Last Updated**: 2026-09-10

Tracking unfinished work that spans sessions.

### Hamle 7 Implementation (historical, abandoned)

### Phase 1: Foundation Fixes (Current)
- [ ] `prompt-counter.sh` — Every 15 prompts, checkpoint memory
- [ ] `session-end.sh` — Rewrite from 500-char to Memory Extractor
- [ ] Align settings.json ↔ CLAUDE.md (hook state consistency)
- [ ] Create state consistency test script

**Status**: 50% (2 hooks done, 2 to go)

### Phase 2: Memory Compiler (Next)
- [ ] Daily/Threads parser
- [ ] Information extractor (Observation/Decision/Lesson)
- [ ] Deduplication engine
- [ ] Conflict detector
- [ ] Importance scorer

**Status**: 0% (design complete, implementation pending)

### Phase 3: Validation & Storage (Future)
- [ ] Memory validator (consistency check)
- [ ] Canonical format definition
- [ ] mem0 auth resolution
- [ ] Dual-write (Obsidian ↔ mem0)

**Status**: Blocked on mem0 auth

### mem0 Integration (historical, abandoned)

- **Issue**: Auth pending
- **Blocker**: Cannot proceed until `~/.mem0/auth.json` configured
- **Action**: Follow mem0-setup.md when auth available

### Navigation Hubs (historical, abandoned; optional enhancement)

- [ ] Create INDEX-Data-Engineering.md (Hamle 7)
- [ ] Create INDEX-Messaging-Events.md (Hamle 7)
- [ ] Create INDEX-Search-Indexing.md (Hamle 7)
- [ ] Create INDEX-Mobile-Development.md (Hamle 7)
- [ ] Create INDEX-Machine-Learning.md (Hamle 7)

**Status**: Nice-to-have (currently have Hamle 3-6 hubs)

---

**Blocking Nothing Critical Right Now** — Phase 1 can proceed independently.
