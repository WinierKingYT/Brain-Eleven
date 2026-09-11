# IG-07 Slice 2A Independent Review

**REVIEWED REPOSITORY:** `WinierKingYT/Brain-Eleven`
**REVIEWED BRANCH:** `master`
**REVIEWED HEAD:** `26f35a67c109ea0d5b78a0a0abcb40f126f4c760`
**REVIEW DATE:** 2026-09-11
**REVIEWER:** Claude session `brain-eleven-66`
**REVIEWER ROLE:** Independent read-only reviewer
**IMPLEMENTATION PARTICIPATION:** None — all three modules were implemented
by Codex; this review neither wrote nor edited `brain_eleven/memory/provenance.py`,
`brain_eleven/runtime/chat_interface.py`, `brain_eleven/runtime/maintenance.py`,
their legacy adapters, or their tests.

## Method

Independently re-run, not read-and-trusted:

- Read every diff (`git show <commit>`) for the module-3 implementation
  (`1295c68`), its tests (`dff9d46`), and the aggregate report (`26f35a6`).
  Modules 1 (`2d90c97`/`288f778`) and 2 (`72f66d9`/`ae63e82`) were already
  reviewed individually earlier this session; re-verified their identity and
  behavioral tests still hold at this HEAD rather than re-reading the diffs.
- Focused suites: `test_runtime_maintenance.py`, `test_post_session_maintenance.py`,
  `test_session_pipeline.py`, `test_pre12_memory_state_caller_migration.py`
  (53 passed, matches report), plus `test_memory_provenance.py` and
  `test_phase11_graph_chat.py` for modules 1/2 (54 passed).
- Full suite at HEAD: **895 passed, 2 warnings** — matches the report exactly,
  no intermittent hook-timing flake this run.
- CI's exact critical lint command (`flake8 ... --select=E9,F63,F7,F82`): 0.
- Clean-interpreter package/legacy/bare object identity check for all three
  modules (module 3 fresh import; modules 1/2 spot-checked with a
  representative symbol each).
- Confirmed by diff stat that `scripts/session_pipeline.py` and
  `.claude/hooks/` are untouched between `ae63e82` and `26f35a6` (module 3's
  range) — the maintenance CLI's subprocess invocation
  (`post_session_maintenance.py --vault ... --generated-by-run ... --quiet`)
  is unchanged in `session_pipeline.py`.
- Grepped `brain_eleven/runtime/maintenance.py` for any `MemoryStore` write
  path: the only canonical-memory interaction is a read
  (`MemoryStore(vault_path).revision()`); confirmed by the new parity test
  asserting the vault's `validated-memory.json` bytes are unchanged after
  `run_maintenance()`.

## Per-module findings

| Module | Canonical target | Adapter shape | Notes |
|---|---|---|---|
| `memory_provenance.py` | `brain_eleven/memory/provenance.py` | Thin adapter, dynamic load, no duplicate logic | Read-only w.r.t. `MemoryStore`, as designed. Re-verified clean. |
| `chat_interface.py` | `brain_eleven/runtime/chat_interface.py` | Same pattern | `handle_create` still refuses direct writes (routes to the validator-gated path). Re-verified clean. |
| `post_session_maintenance.py` | `brain_eleven/runtime/maintenance.py` | Same pattern; `_load_canonical` mirrors prior slices' loader | New this round — reviewed in full below. |

### Module 3 detail (`post_session_maintenance.py` → `maintenance.py`)

- `brain_eleven/runtime/maintenance.py` is a straight move of `_run_step`,
  `run_maintenance`, `save_report`, `summarize_for_shell`, and `main` with no
  behavior change: same three best-effort steps (graph rebuild, anomaly
  detection, digest), same atomic tmp-file report write, same "always return
  0" contract (maintenance is best-effort, never a session-end gate).
- `scripts/post_session_maintenance.py` is adapter-only: AST check confirms
  the only function defined in the legacy file is `_load_canonical`; every
  public name is re-bound from the canonical module. The new
  `test_legacy_script_is_an_adapter_only` test enforces this structurally,
  not just by report claim.
- CLI parity (`--vault`, `--generated-by-run`, `--quiet`) verified via a real
  subprocess invocation in `test_legacy_cli_preserves_quiet_and_generated_by_run`,
  not just a unit-level call — this is a stronger check than modules 1/2 used
  and a good pattern to carry into future slices.
- `main()` gained an optional `argv` parameter (old code called
  `parser.parse_args()` with no args); this is additive for testability and
  does not change the CLI's observed behavior when invoked normally.

## Regression

- Focused (53 collected across maintenance/pipeline/migration): reproduced,
  53/53 passed.
- Modules 1/2 behavioral suites: reproduced, 54/54 passed.
- Full suite: **895 passed, 2 warnings** — matches the report; no flake
  surfaced this run (the hook-timing flake noted in Slice 1's review did not
  reproduce here, consistent with it being intermittent rather than fixed or
  worsened by this slice).
- `flake8 --select=E9,F63,F7,F82` over CI's exact scope: 0.

## Safety / scope

No canonical authority (`MemoryStore`, `StateStore`, `ProjectRegistry`) write
path was added anywhere in Slice 2A. `session_pipeline.py`'s subprocess
arguments and the hook budget are unchanged, confirmed by diff, not just by
report claim. All three legacy scripts remain importable and directly
executable (adapter/CLI parity tests cover this explicitly).

## P0 / P1 Findings

None.

## P2 Findings

None new. The two P2 items already open from Slice 1 (`anomaly.py`'s
`sys.modules.get` lookup pattern; a hook-timing stabilization pass) remain
open and unaffected by this slice.

## Final Verdict

**SHIP** — IG-07 Slice 2A (`memory_provenance.py`, `chat_interface.py`,
`post_session_maintenance.py`) is accepted. Canonical authority, capture,
retrieval, and Phase 20 paths remain untouched. `task_state_context.py`
stays excluded pending its own migration plan. The next sub-slice (2B:
`entity_extractor.py` + `knowledge_graph.py`, per `IG07-SLICE2-PLAN.md`)
requires its own bounded contract before implementation begins, per this
project's standing rule.
