# W-22 — V2 Optional-Omission Contract

**Status:** CONTRACT REVIEW PENDING — implementation not started
**Contract base:** exact repository head `8ea6a99`
**Program:** Engineering Weak-Point Improvement Goal
**Phase 20:** FROZEN / LOCKED — **V2:** SHADOW

## Objective

Make `BudgetContract.allow_optional_omission` an enforced, observable policy
boundary. When it is `False`, the V2 compiler must not silently drop optional
context because of a profile cap, optional budget, item limit or final rendered
budget overflow.

## Observed weakness

`BudgetContract` validates and serializes `allow_optional_omission`, but
`context_compiler_v2.planner.choose()` and the compiler's final rebalance pass
do not consume it. A caller can therefore request omission disallowance while
the compiler returns a successful or degraded bundle with optional items
omitted under `profile_budget_exhausted`, `profile_item_limit` or
`budget_exhausted`.

## Bounded behavior contract

1. **Shadow-only boundary.** Change only V2 budget planning/rebalance behavior.
   Do not promote V2, alter Router/authority/retrieval/ranking, change
   provider selection, modify canonical stores, alter SessionStart/client
   delivery or unlock Phase 20.
2. **Default compatibility.** `allow_optional_omission=True` preserves current
   planner, omission reasons, ordering, status and telemetry byte-for-byte for
   existing requests.
3. **False means no optional omission.** With
   `allow_optional_omission=False`, every otherwise eligible optional draft
   must fit the caller's usable token/byte budget and configured profile item
   cap. If any optional draft would be omitted for `profile_budget_exhausted`,
   `profile_item_limit` or `budget_exhausted`, compilation returns
   `INSUFFICIENT_BUDGET` with the exact stable error
   `OPTIONAL_OMISSION_DISALLOWED`. The result exposes no model-facing rendered
   context and does not claim successful optional coverage. Bounded omission
   metadata may list only counts/roles, never text or prompts.
4. **Final rebalance.** If the final renderer measurement exceeds the budget
   and optional omission is disallowed, return the same visible failure before
   removing an optional draft. The existing mandatory-overflow behavior keeps
   its precedence and error/warning contract.
5. **All-fit success.** If every eligible optional draft fits both the planner
   limits and final rendered budget, `allow_optional_omission=False` produces
   the same selected context and status as the default policy.
6. **No hidden authority.** The flag controls only omission policy. It cannot
   widen scope, alter lifecycle/authority decisions or write MemoryStore,
   StateStore, ProjectRegistry, compiler cache or other canonical data.
7. **Bounded diagnostics.** Failure telemetry may expose only counts, budget
   values and stable omission reasons. It must not expose candidate text,
   prompts, transcripts, secrets or raw memory content.

## Required tests

- `allow_optional_omission` round-trips through `BudgetContract` and request
  serialization.
- With `False`, a profile-budget, profile-item-limit and optional-token
  overflow each return `INSUFFICIENT_BUDGET` with
  `OPTIONAL_OMISSION_DISALLOWED`, no rendered context and no silent success.
- With `False`, a final renderer overflow fails before optional removal.
- Mandatory overflow retains its existing precedence and diagnostics.
- With `False` and all optional drafts fitting, output matches the default
  policy; with `True`, existing omission behavior remains unchanged.
- Default public/holdout compiler inputs remain byte-identical and no
  canonical/cache write is introduced by a failed compilation.
- Failure output remains content-free and deterministic.

Run focused planner/compiler tests, then the full suite, critical flake8
(`E9,F63,F7,F82`), compileall and `git diff --check` at an exact committed
revision. Evaluation corpora, labels, thresholds and providers remain
immutable.

## Exit gate

W-22 may be marked `SHIP` only after an independent contract review returns
`SHIP`, implementation and focused tests pass, exact-head full regression is
green, and an independent read-only implementation review returns exactly
`SHIP`.

Until then: **W-22 = OPEN / NOT ACCEPTED**.
