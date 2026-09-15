# W-17 Runtime-Owned Path Containment — Independent Review

**Implementation/test revision:** `6017255c3405dfdbc8d9d154498c7a5edd5f7649`
**Final documentation revision:** `7c159a35dacc067fde83ea4f350b9af5a6f33e1f`
**Reviewer:** `/root/w10_exact_review` (read-only, independent context)
**Verdict:** **SHIP**

## Scope reviewed

The reviewer checked the W-17 contract, implementation diff, caller routing,
runtime path safety, lock behavior, focused tests, full regression and static
gates. The review was bounded to vault-owned `.brain-eleven/runtime/**` and
did not accept changes to canonical MemoryStore/StateStore/ProjectRegistry,
host Claude/Codex configuration, HOLDOUT evaluation data, V2 promotion or
Phase 20.

## Evidence

- Selected-vault validation, ancestor containment, runtime-root creation,
  final-file symlink, direct ancestor, `..` escape and Windows junction/reparse
  cases fail closed.
- Runtime JSON publication retains atomic temp-file, flush, fsync and replace
  behavior with identity checks before bytes are written and before publish.
- POSIX runtime locks use target-specific descriptor-relative markers and
  `flock`; Windows uses target-scoped named mutexes. Lexical aliases normalize
  to one lock identity, and distinct targets remain independent.
- W-15 runtime-config CAS/lock behavior and existing runtime caller paths
  remain green. The legacy canonical `scripts/memory_store_lock.py` surface is
  unchanged.
- Focused W-17/W-15/IG-00/PRE-13/W-07B/capture set: **118 passed, 2 warnings**
  at the implementation evidence run; the final W-17/W-15/lock set: **34
  passed**.
- Full suite at the exact implementation revision: **1264 passed, 2
  warnings**.
- Critical flake8 (`E9,F63,F7,F82`), compileall and diff checks passed.

## Findings

No new P0, P1 or P2 issue remained after the descriptor-relative lock and
target-isolation hardening. The two dependency deprecation warnings are
pre-existing and unrelated to W-17.

**SHIP** — W-17 runtime-owned path containment is independently accepted.
