# Phase 17 — Task-Aware Context Router Contract

## Purpose and boundary

Phase 17 accepts the immutable Phase 16 `TaskStateContext` and produces a
content-free `RetrievalPlan` plus `RouterResult`. It identifies candidate
canonical references only. It does not resolve authority or conflict, choose
final context, enforce a token budget, replace `ContextCompiler`, or alter
SessionStart.

The only supported rollout modes are `OFF` and `SHADOW`. Shadow results are
diagnostic; they are never injected into a prompt. Rollback is setting the
trusted caller's mode to `OFF`.

## Authorities and non-mutation rule

`MemoryStore` remains the authority for durable memory, `ProjectRegistry` for
project identity and lifecycle, and `StateStore` for current project truth.
The router is read-only against all three. Graph and cache are derived state:
the router never rebuilds, repairs, or writes the graph; it may discard a
corrupt/stale cache.

`TaskEnvelope` and the canonical memory schema are unchanged. A route result
contains IDs, types, lifecycle, revisions, match signals, and retrieval scores;
it never serializes memory text or state text. Retrieval score is not authority
or final-context score.

## Trusted policy

`RoutingOptions` is the only authority for scope, lifecycle history and
rollout mode. Raw user text can affect deterministic profile selection and
query terms, but cannot widen those permissions.

| Scope | Allowed canonical memory |
|---|---|
| `CURRENT_PROJECT` | Resolved current project; permitted global memory after strict same-project retrieval is sparse. |
| `GLOBAL_ONLY` | Global memory only. |
| `SELECTED_PROJECTS` | A finite, explicit trusted project list, which must include the resolved task project; permitted global memory. |

There is no `all projects` scope. `ACTIVE_ONLY` is the default lifecycle
policy. Historical and archived access require explicit trusted options.

## Deterministic routing

Profiles are `continuation`, `implementation`, `debugging`, `architecture`,
`review`, `research`, and `general`. Continuation takes precedence over intent
when the task has a continuation identifier or a bounded continuation phrase.

The query planner runs offline in a fixed order: direct memory ID, artifact,
exact entity, concept, domain, state, continuation, aliases, then graph
relation expansion. Retrieval first searches strict in-scope active records.
Only then may it use permitted global records, aliases, or the graph. Scope
never expands implicitly.

Memory and state are loaded as canonical revision snapshots. The router checks
their revisions again at completion, retries one time on a race, then returns
`STALE_INPUT`. A TaskStateContext whose state snapshot has already changed is
also `STALE_INPUT`. Corrupt canonical memory/state/config is a fail-closed
`FAILED` result; it is never treated as empty.

The graph is eligible only when its source memory revision is fresh. A missing,
corrupt, or stale graph is skipped, preserving canonical candidates and marking
the result `DEGRADED`.

## Result and privacy contract

The only statuses are `SUCCESS`, `DEGRADED`, `EMPTY`, `STALE_INPUT`,
`INVALID_TASK`, `SCOPE_ERROR`, and `FAILED`. Candidate IDs are deduplicated;
their query provenance and retrieval signals are merged deterministically.

The optional cache is derived, bounded, revision-keyed and content-free. CLI
JSON, shadow reports, route evaluation and telemetry are content-free. The
offline Phase 15 adapter resolves synthetic fixture IDs to text only inside the
evaluation process, preserving the existing evaluator contract without putting
text into router output.

## Graduation gates

Phase 17 cannot be called graduated until revision-bound CI, public + holdout
evaluation, route expectations, performance evidence and an independent
read-only review are green. Required hard gates are zero wrong-project route,
implicit cross-project route, forbidden inactive leakage, prompt policy
override, stale-graph acceptance, canonical-as-empty acceptance,
nondeterminism and canonical writes.
