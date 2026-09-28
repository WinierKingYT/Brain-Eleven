# IG-02 Native Client Smoke Evidence

**Revision under test:** `29d4e28a50625625406b1795fd4296238a892520`  
**Date:** 2026-09-09  
**Evidence class:** GENERATED EVIDENCE / content-free

The real Claude and Codex executables were run from an isolated temporary
vault and isolated client configuration directory.  No live client settings,
vault data, prompt, transcript, token or memory content is included here.

| client | event(s) observed | exit code | queue event id | terminal state | canonical verification | config mutation | trust verdict |
|---|---|---:|---|---|---|---:|---|
| Claude executable | SessionStart, UserPromptSubmit, SessionEnd hook invocations | 1 | `NOT_EMITTED_TRANSCRIPT_UNAVAILABLE` | `NOT_REACHED` | `NOT_REACHED` | 0 | `BOUNDED_UNVERIFIED_API_AUTH` |
| Codex executable | SessionStart/UserPromptSubmit hook invocation | 1 (terminated after network retry) | `NOT_EMITTED_TRANSCRIPT_UNAVAILABLE` | `NOT_REACHED` | `NOT_REACHED` | 0 | `BOUNDED_UNVERIFIED_NETWORK_AUTH` |
| Native launcher golden fixture | SessionEnd → queue → worker | 0 | `HASH_ONLY_EVENT_ID` | `COMPLETED` | `VERIFIED` | 0 | `SYNTHETIC_GOLDEN_PASS` |

The real-client rows prove that the installed hook definitions were loaded and
invoked without a visible window, but the local environment could not supply
Claude API authentication or Codex network access, so those runs did not
produce a client-owned transcript for autonomous queue capture.  The complete
queue, receipt and canonical-effect path is verified by the content-free
launcher golden tests and the Claude/Codex transcript-shape runtime tests.

The bounded exception remains explicit: live client trust and real-client
autonomous capture are not claimed as verified until an authenticated,
network-enabled smoke can be run in a separately approved environment.

## 2026-09-28 PR32 isolated native recheck

**Harness revision:** `97201b0e53e5a4487e8357ab741f55431c4aedef`

**Evidence class:** GENERATED EVIDENCE / content-free

The revised harness was run against the isolated temporary client profiles.
No prompts, responses, credentials, memory content or local paths are retained.

| client / stage | attempts | auth evidence | SessionStart | UserPromptSubmit | queue / canonical effect | isolation | result |
|---|---:|---|---|---|---|---|---|
| Claude, before re-authentication | 2 | Authentication not verified; direct no-tools request returned an auth error | DELIVERED (2/2) | EMITTED, but not delivered (2/2) | No committed queue job or verified effect | Live settings hash and memory revision unchanged | `BOUNDED_UNVERIFIED_CLAUDE_AUTH` |
| Claude, after re-authentication | 2 | `loggedIn=true`, provider `claude.ai`; direct no-tools request returned HTTP 429 | DELIVERED (2/2) | EMITTED, but not delivered (2/2) | No committed queue job or verified effect | Live settings hash and memory revision unchanged | `BOUNDED_UNVERIFIED_CLAUDE_API_429` |
| Codex | 0; preflight stopped | Not reached | Not reached | Not reached | Not reached | No configuration mutation | `BOUNDED_UNVERIFIED_CODEX_HOOK_BINDING` |

The Claude subscription login command completed successfully and the isolated
auth-status response confirmed a signed-in `claude.ai` profile. A fresh
tools-disabled request then returned HTTP 429 with an API-error terminal state;
after a one-minute cooldown, both native smoke attempts still exited
unsuccessfully. No response text is retained. The isolated Codex preflight
found that the four expected hook entries were recorded in the installation
manifest but were absent from the active temporary hooks configuration, so it
did not launch the Codex client or rewrite that configuration. The registered
configuration target matched the isolated profile in both checks.

W-07B native acceptance remains incomplete. Claude's current blocker is the
API 429 after successful sign-in. Codex hook review/activation in the isolated
profile remains pending; latency and multi-session dogfood runs remain
unclaimed.
