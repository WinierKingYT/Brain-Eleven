# Architecture

One page. If something here goes stale, fix this file — don't start a
parallel one.

## The three layers

```
┌─────────────────────────────────────────────────────────┐
│  Vault (📝 Template/, 🔮 Companion/, 🗂️ Proje Notları/)  │  ← the actual second-brain
│  Obsidian markdown notes. This is the product's data.    │     content a user reads/writes
└─────────────────────────────────────────────────────────┘
              ▲ read/write via hooks (SessionStart, capture)
┌─────────────────────────────────────────────────────────┐
│  brain_eleven/  (current package and migration target)   │
│    memory/store.py  projects/registry.py  state/store.py │
│    graph/ extraction/ retrieval/ search/ runtime/ ...    │
└─────────────────────────────────────────────────────────┘
              │ brain_eleven/_legacy.py loads selected modules
┌─────────────────────────────────────────────────────────┐
│  scripts/  (remaining legacy implementations/adapters)  │
│    e.g. context-compiler.py, hybrid-search.py, ...       │
└─────────────────────────────────────────────────────────┘
```

The migration is incremental, but `brain_eleven/` is not just a future target:
the canonical memory, project registry and state stores are implemented there.
`brain_eleven/_legacy.py` loads selected remaining `scripts/*.py` modules by
path and caches them so callers share one module identity. When changing
behavior, start from the package surface and trace its callers; use the bridge
to identify any behavior still delegated to `scripts/`. Do not assume either
directory is authoritative for every subsystem. The remaining migration work
is tracked under IG-07 in `docs/programs/INTELLIGENCE-GRADUATION.md`.

## Canonical authority (who owns which fact)

- **`MemoryStore`** (`brain_eleven/memory/store.py`) — durable history. Every
  canonical write goes through here: revisioned, locked, atomic. Nothing else
  writes canonical memory directly.
- **`ProjectRegistry`** (`brain_eleven/projects/registry.py`) — project identity
  and lifecycle (which project a memory/state belongs to, active/archived).
- **`StateStore`** (`brain_eleven/state/store.py`) — mutable *current* project truth
  (as opposed to `MemoryStore`'s append-only history).

Graph, search, context and routing layers consume these authorities or derived
views of them. Any canonical mutation must cross the relevant store boundary;
derived indexes and context are not alternate authorities.

## V1 vs. V2 (shadow) retrieval

- **V1** is the retrieval/compilation path actually wired into SessionStart
  today — `scripts/context-compiler.py`, `scripts/hybrid-search.py`,
  `scripts/memory-retriever.py`.
- **V2** is a set of standalone, read-only candidate modules that do **not**
  inject into any live session yet: `context_router/`, `authority/`,
  `context_compiler_v2/`, `context_density_v2/`, `retrieval_decision_v2/`.
  Each is evaluated against V1 via `evals/*_shadow.py` / `evals/*_benchmark.py`
  before any promotion decision. Check `PROJECT-STATUS.md` for the current
  SHADOW/CANARY/DEFAULT state of each — do not assume a V2 module is live
  just because its code exists.

## Evaluation (`evals/`)

Deterministic, offline evaluators and corpora (`evals/corpus`,
`evals/corpus-v2`, `evals/fixtures`) measure retrieval/extraction quality
without touching a real model. `evals/baseline_snapshot.py` pins a
content-fingerprinted expected result (`evals/reports/baseline-v3.json`) so a
silent behavior change fails a test instead of going unnoticed. If that test
fails, don't edit the JSON by hand — regenerate it deliberately and explain
why the baseline moved.

## Hooks / runtime (`brain_eleven/runtime/`, `.claude/`)

`SessionStart`, `UserPromptSubmit` and capture hooks call into
`brain_eleven`/`scripts` to load context and queue captured memories. See
`RUNTIME-DATAFLOW.md` for the exact installed-vs-repository path mapping —
that file is the source of truth for "what actually runs when Claude starts,"
not this one.

## What to read for current status vs. architecture

This file describes shape and stays true across packages. For "is X actually
done," read `PROJECT-STATUS.md` instead — status changes weekly, architecture
shouldn't.
