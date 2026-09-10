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
│  brain_eleven/  (target implementation, "strangler")     │
│    memory/  projects/  state/  graph/  extraction/       │
│    retrieval/  search/  lifecycle/  support/  runtime/   │
│    infrastructure/                                        │
└─────────────────────────────────────────────────────────┘
              │ brain_eleven/_legacy.py loads these on demand
┌─────────────────────────────────────────────────────────┐
│  scripts/  (original implementation, ~60 files)          │  ← most real logic still
│    memory_store.py, project_registry.py, state.py,       │     lives here today
│    context-compiler.py, hybrid-search.py, ...             │
└─────────────────────────────────────────────────────────┘
```

`brain_eleven/` is the package everything is *supposed* to move into
(see `brain_eleven/__init__.py`: "Migration is intentionally incremental").
`brain_eleven/_legacy.py` is the bridge: it loads a `scripts/*.py` module by
path and caches it, so callers get one module identity instead of two copies
of the same logic. When you need to change behavior, find the real
implementation in `scripts/` first — `brain_eleven/` may just be a thin
re-export until that file's migration lands (tracked as IG-07 in
`INTELLIGENCE-GRADUATION.md`).

## Canonical authority (who owns which fact)

- **`MemoryStore`** (`scripts/memory_store.py`) — durable history. Every
  canonical write goes through here: revisioned, locked, atomic. Nothing else
  writes canonical memory directly.
- **`ProjectRegistry`** (`scripts/project_registry.py`) — project identity
  and lifecycle (which project a memory/state belongs to, active/archived).
- **`StateStore`** (`scripts/state.py`) — mutable *current* project truth
  (as opposed to `MemoryStore`'s append-only history).

Everything downstream (graph, search, context compiler, router, authority
resolver) *reads* these three; none of them get a second write path.

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
