# Runtime dataflow and authority

Authority: **CURRENT**. Audit date: 2026-09-09. This map distinguishes repository
implementation, installed configuration and verified client execution. ACTIVE
means a configured/code path, not native trust or successful real-use graduation.
See IG00-FREEZE-BASELINE for exact revision and review limitations. The latest
revision-bound Validation evidence is run 34378278695 at
`29d4e28a50625625406b1795fd4296238a892520`; the PRE-13 runtime run
34378278696 passes its Ubuntu/Windows infrastructure jobs while its historical
quality job remains a visible failure.

## Observed checkpoint behavior and delivery ownership

At preserved development checkpoint `7e6f55a82465f6fef7abf8318a451308bbe9a0e9`,
native Claude/Codex SHADOW starts the service on SessionStart and computes V2 on
UserPromptSubmit without emitting its context. Repository legacy shell hooks
exit when `native-hooks-installed.json` exists. An independently installed global
Claude V1 SessionStart hook is also configured; it is not identical to the
repository hook. Therefore “all legacy disabled” and “native SHADOW delivers V1”
are both false descriptions of that checkpoint.

IG-00's implemented correction routes native SessionStart through the existing
V1 compiler's ranking, typed state and renderer with only safe canonical
project/global inputs, a conservative budget and final scope/revision checks.
Unscoped Last Session, Open Loops and linked-note inputs are excluded. The
installer journals and suspends only exact known global Brain-Eleven legacy
commands, restoring them on uninstall. Focused tests and the current real install
reconciliation passed; installed hook trust
and actual client delivery require separate native evidence. Unrelated global
hooks are outside Brain-Eleven ownership and must be preserved.

An isolated native smoke on 2026-09-08 exercised the installed hook definitions
without touching the user's vault or client configuration. Claude produced
successful native `SessionStart` and `UserPromptSubmit` responses; Codex
produced a successful native `UserPromptSubmit` response after its temporary
hook definition was explicitly trust-bypassed for the test. Separate Golden
E2E launcher runs for both client transcript shapes reached queue terminal
states and verified canonical effects. These results prove the bounded hook
and queue paths, not trust of the user's live installation or successful model
authentication.

The IG-02 exact-head smoke on 2026-09-09 repeated the executable checks in an
isolated vault. Claude and Codex both invoked native hook entry points without a
visible window, but the local Claude API authentication and Codex network
failure prevented a client-owned transcript from reaching the queue. This is
recorded as a bounded unverified trust result in
`IG02-NATIVE-SMOKE-EVIDENCE.md`; the launcher golden path separately verifies
queue completion, effect receipt and canonical verification.

## Paths and node states

| Node / entry | State | Actual behavior and boundary |
|---|---|---|
| Native Claude/Codex SessionStart | ACTIVE V1 path in current implementation | Opt-in scope/config check, local service startup and bounded canonical V1 bootstrap. OFF emits none; focused tests and installed reconciliation passed. Native trust remains unverified. Checkpoint behavior differed as recorded above. |
| Native UserPromptSubmit | SHADOW | Service context request runs TaskStateComposer → Router → Authority → Retrieval Decision → Density → V2 Compiler; baseline comparison records IDs. No V2 injection in SHADOW. |
| Native Stop / SessionEnd | ACTIVE capture handoff | Bounded event metadata enters durable queue; hook does not read the full transcript or perform extraction. Duplicate events are idempotent. |
| Repository shell hooks | LEGACY | SessionStart V1 compiler/bootstrap and SessionEnd handoff retained; native installation marker currently suppresses them. Not equivalent to global copied hooks. |
| Installed global Claude V1 hook | LEGACY, observed configured active before reinstall | Updated installer reversibly suspends exact owned legacy commands; actual reinstall reconciliation and native execution proof pending. |
| `/remember` → remember CLI | MANUAL | Explicit user capture uses canonical memory validation/write boundary; not a native worker job or proof of autonomous capture. |
| API capture / updates | ACTIVE when API service runs | API safety/scope validation → canonical MemoryStore transaction/CAS. Separate from native service queue and not model-authorized truth. Deployment is optional. |
| Durable Queue | ACTIVE | Persistent queued/processing/completed/dead-letter state, leases, retries and recovery. `COMMITTED` is acknowledged only after a matching content-free `EFFECT_VERIFIED` receipt; a terminal no-evidence/review outcome does not assert a new memory. |
| Local worker | ACTIVE when local service runs | Automatically drains allowed jobs; legacy standalone worker invocation remains MANUAL. Incremental evidence cursor precedes extraction; canonical/review effects are recorded in a durable receipt before queue acknowledgement, and replay skips an already verified effect. |
| Evidence reader/store | ACTIVE | Claude/Codex transcript increments validated; store retains metadata, not transcript copies. Missing/corrupt evidence fails visibly through retry/dead-letter. |
| Deterministic extraction | ACTIVE | Structured candidates from bounded evidence; remains the current primary extractor. Semantic IG-03 replacement is not implemented by this map. |
| Optional loopback model | SHADOW / disabled by default | Proposes bounded review candidates only, never canonical truth. |
| Review | ACTIVE proposal path | SHADOW candidates require review; acceptance is blocked outside CANARY/ACTIVE. Rejection/expiry removes retained proposal text. |
| Truth / lifecycle | ACTIVE canonical boundary | MemoryTruth validates candidates and lifecycle operations; runtime automatic writes only in CANARY/ACTIVE, not current SHADOW. Unknown correction targets abstain/review. |
| Typed state boundary | ACTIVE canonical boundary | Requirements/blockers routed through StateStore validation, CAS and durable operation receipts. Runtime write gate matches truth gate. |
| MemoryStore / StateStore / ProjectRegistry | ACTIVE canonical authorities | Only authoritative memory, typed state and project identity/scope. Graph, bootstrap, model and telemetry are derived/non-authoritative. |
| Router / Authority | SHADOW in native path | Scoped read-only references, canonical/lifecycle resolution and revision checks. Available to offline/manual callers too. |
| V2 Compiler | SHADOW in native path | Canonical rehydration, selected needs, conservative budget, safety and final revision/scope checks. Manual CLI can inspect output; that is not native production promotion. |
| V1 compiler / bootstrap | LEGACY production compatibility | Existing SessionStart reference path; bootstrap is validated derived context, never a canonical store. V1 remains the intended user-visible owner until IG-06. |

No implementation is declared DEPRECATED merely because a replacement is
planned. Retirement/deprecation is an explicit later IG-06/07 decision.

## Data flow and gates

```text
Native Stop/SessionEnd → bounded event → Queue → local Worker
  → incremental Evidence → deterministic Extraction → structured candidate
  → SHADOW: Review
  → CANARY/ACTIVE only: deterministic Truth or typed State → canonical commit
  → verified operation receipt / review / no-effect outcome → queue terminal state

Native task → Task + State → Router → Authority → Retrieval Decision
  → Density/minimum context → V2 Compiler → final scope/revision recheck
  → SHADOW: content-free observation only
  → CANARY/ACTIVE only: native context delivery

Manual Remember / API → deterministic validation → canonical MemoryStore
Canonical stores → derived graph/bootstrap/context (never reverse authority)
```

OFF suppresses native runtime work. Current local configuration is SHADOW with
Brain-Eleven opt-in; other projects are not automatically enrolled. Existing
CANARY requires migration, allowed projects and frozen PRE-13 quality gates;
ACTIVE additionally validates real-use evidence. Neither gate is an IG-06
promotion permission: IG sequence still applies. Synthetic CANARY fixtures do
not describe the real vault. MIRROR/DEFAULT and final V1 retirement are program
stages to contract later, not current configuration values.

Raw transcript files remain client-owned. Safe review proposal text expires
after seven days of operational cleanup, or on acceptance/rejection; physical
cleanup waits if the service is offline. Telemetry excludes prompt/context text.
Windows native launchers use windowless Python; agent verification must also
remain hidden. Service startup is on demand, idle shutdown is fifteen minutes,
and native trust is never inferred from `doctor` saying configured.
