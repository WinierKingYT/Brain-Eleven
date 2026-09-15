# W-19B — Native Hook Health Contract

**Status:** CONTRACT REVIEW PENDING — implementation not started

**Program:** Engineering Weak-Point Improvement Goal

**Phase 20:** FROZEN / LOCKED — **V2:** SHADOW

## Objective

Make native hook health truthful at the existing derived diagnostics boundary.
When a hook cannot deliver context or capture an event, its durable
`last-hook.json` status and `doctor()` result must show a degraded condition;
normal return from the launcher must not turn a warning into `OK`.

## Observed weakness

`brain_eleven/runtime/launcher.py::main` records `status="OK"` whenever
`hook()` returns normally. `hook()` can return a bounded `systemMessage` when
the service is unavailable or a native delivery is unusable, so the durable
breadcrumb becomes false green. `brain_eleven/runtime/install.py::doctor`
does not use that native status when deciding `READY`/`ATTENTION` and reads the
legacy SessionStart breadcrumb without a race-safe default.

## Bounded behavior contract

1. Keep the existing native hook output, timeout, privacy and event behavior
   unchanged. After a normal `hook()` return, write `last-hook.json` with
   `status="DEGRADED"` when the bounded output contains `systemMessage`, and
   `status="OK"` otherwise. Exception handling remains `DEGRADED`.
2. Preserve the existing content-free fields (`at`, `client`, `event`,
   `elapsed_ms`) and do not persist prompts, transcripts, tokens, exception
   text, context or memory content.
3. `doctor()` must read `last-hook.json` with a safe missing/corrupt default.
   The latest native `DEGRADED` status makes the existing overall status
   `ATTENTION`; a missing or valid `OK` breadcrumb does not by itself degrade
   an otherwise healthy installation. Legacy SessionStart failure behavior
   remains unchanged.
4. Client configuration, service lifecycle, canonical MemoryStore/StateStore/
   ProjectRegistry, capture effects, retrieval, V2 and rollout modes are
   untouched. This is a diagnostics projection only.
5. A later successful native invocation overwrites the breadcrumb with `OK`;
   no historical log or new persistence authority is introduced.

## Required tests

- service-unavailable `SessionStart` returning a warning persists `DEGRADED`;
- warning-free native hook persists `OK`;
- exception path remains `DEGRADED` and content-free;
- `doctor()` reports `ATTENTION` for the latest native degraded breadcrumb;
- missing/corrupt breadcrumb is bounded and does not crash doctor;
- a later successful hook clears the degraded diagnostic;
- existing legacy SessionStart failure test remains unchanged;
- no MemoryStore/StateStore/ProjectRegistry revision or content changes.

Run the focused launcher/install/session-start suites, then full
`pytest tests -q`, critical flake8 (`E9,F63,F7,F82`), compileall and
`git diff --check` at an exact committed revision.

## Scope exclusions

This package does not change native client trust verification, hook commands,
latency budgets, SessionStart context generation, maintenance delivery,
retrieval ranking, V2 promotion, automatic Markdown writes, canonical stores
or Phase 20. Those remain separate W-07B or later packages.

## Exit gate

W-19B may be marked `SHIP` only after contract-independent review returns
`SHIP`, implementation/tests satisfy this contract, exact-head regression is
green, and an independent read-only implementation review returns exactly
`SHIP`.

Until then: **W-19B = OPEN / NOT ACCEPTED**.

**Contract status: REVIEW PENDING — implementation başlamadı.**
