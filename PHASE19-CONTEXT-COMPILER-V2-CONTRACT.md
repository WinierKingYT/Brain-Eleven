# Phase 19 — Context Compiler V2 + Token Budgeter Contract

## Purpose

Phase 19 turns a validated Phase 16 `TaskStateContext` and a Phase 18
`ResolutionResult` into a bounded, model-facing `ContextBundle`. It answers
which already-resolved records deserve scarce context; it does not retrieve,
infer authority, resolve conflicts, or write canonical data.

## Fixed boundaries

- Canonical memory, state, registry, graph, Router, Authority Resolver,
  SessionStart, and the V1 ContextCompiler remain unchanged.
- The compiler supports only `OFF` and `SHADOW`. It never injects V2 output
  into a session or prompt automatically.
- Canonical references are rehydrated only after their memory/state revisions
  match the Phase 18 snapshot. A changed input produces `STALE_INPUT`.
- A project candidate outside the task project is an explicit
  `UPSTREAM_INVARIANT_VIOLATION`, not a quietly filtered result.
- Global-only tasks may consume global memory only. Project task context may
  consume its project and global memory; another project never enters V2.

## Compilation policy v1

`context_compiler_v2` uses deterministic, explainable classifications:

1. Reject invalid lifecycle, historical-by-default, secret-bearing, and exact
   duplicate candidates.
2. Assign a typed role and tier. Constraints, requirements, implementation
   gaps, and unresolved conflicts are Tier 0 mandatory. Current state and
   authoritative decisions precede supporting and optional material.
3. Reserve caller-owned headroom. `max_context_tokens` is a ceiling, never a
   target fill level; `hard_byte_limit` is a second safety boundary.
4. Select mandatory records before optional records. If mandatory context does
   not fit, return `INSUFFICIENT_BUDGET`; never blind-truncate it.
5. Render compact named sections, remeasure the finished artifact, and remove
   only optional entries in a bounded rebalance pass.

There is no hidden authority/utility scalar. Selection ledgers carry role,
tier, canonical reference, compression mode, and an explicit selection or
omission reason.

## Token accounting

The default `utf8-conservative-v1` estimator reports
`CONSERVATIVE_ESTIMATE`. It is not an exact Claude or OpenAI tokenizer and
documentation must not claim otherwise. The manifest records adapter, version,
byte count, estimate, usable budget, and headroom.

## Safety and privacy

- Secret-shaped records are omitted before rendering.
- Reserved Brain-Eleven delimiters inside source text are escaped and source
  text is always rendered as untrusted context, never as instructions.
- Cache, shadow report, telemetry, and `manifest_dict()` are content-free.
  Only an explicit model-facing bundle/CLI output carries selected text.
- Cache is derived, revision-bound, atomic, bounded, and ignored when corrupt.
- Compiler execution performs no canonical write.

## Interfaces

```text
bundle = ContextCompilerV2(vault).compile(
    CompilationRequest(task_state, resolution_result, budget)
)
```

```text
python -m context_compiler_v2 compile --vault . --request-file request.json --json
python -m context_compiler_v2 shadow --vault . --project-root . --request "..." --json
```

Use `--manifest-only` for content-free diagnostics. The `shadow` command does
not alter SessionStart or inject output into a model context.

## Evaluation and graduation

The offline synthetic policy corpus has 180 public and 40 holdout cases across
tight/large budgets, duplicate and conflict-heavy inputs, current-state and
requirement-heavy work, historical context, profile variants, and malicious
source text. It exercises budgets 512, 1024, 2048, 4096, and 8192.

Phase 19 can graduate only after all of the following are revision-bound:

- full public + holdout policy evaluation passes;
- V2 selection evaluation has zero wrong-project and forbidden leakage;
- shadow remains non-injecting and preserves all hard gates;
- the offline 100/1,000/10,000-memory informational compilation benchmark
  records p50/p95 without imposing an absolute latency gate;
- CI security/coverage gates are green; and
- an independent read-only review returns `SHIP`.

Until then V2 remains `SHADOW`; V1 remains the active compiler.

The first local shadow comparison intentionally records a lower candidate
relevance/recall result than V1. That is a diagnostic baseline, not a reason
to weaken safety gates or promote V2; Phase 19 stays shadow-only until a later
review approves a measured improvement.
