# Phase 13 Plan — Cross-Project Memory Capture

**Status:** Implemented in the working tree; runtime verification pending.
**Audience:** An engineer or agent with no prior context on this
conversation. Everything needed to execute is below; verify claims
rather than trusting this document blindly — it was written from a
planning discussion, not from re-reading every line of code fresh.

### Implementation result

The Phase 13 changes are now present in the working tree:

- `scripts/remember.py` provides deliberate, atomic single-memory capture
  with project provenance and graph rebuild.
- `scripts/remember_opt_in.py` provides the fail-closed absolute-root opt-in
  check used by the global session gate.
- `.claude/remember-config.json` is present locally and ignored by Git; it is
  empty by default, so proactive capture remains disabled until explicitly
  opted in.
- The global `/remember` command, global SessionEnd gate, validator/API
  provenance plumbing, tests, and status documentation were added or updated.

The implementation has been statically checked, but the local machine does
not currently provide a runnable Python/pytest environment, so the test suite
still needs runtime verification in an environment with Python installed.

---

## 1. Background

Brain-Eleven is a personal memory system for Claude Code. Phases 1–12
(already built, tested, and merged into `master`) gave it:

- A memory pipeline: `memory-compiler.py` → `memory-validator.py` →
  `memory-lifecycle.py`, writing to `.claude/validated-memory.json`
  (immutable ULID identity, SHA256 fingerprint dedup, quality scoring,
  conflict detection).
- A REST API (`scripts/search-api.py`, FastAPI) exposing search, chat,
  memory CRUD, a knowledge graph, caching, and auth.
- Session hooks (`.claude/hooks/session-start.sh`,
  `.claude/hooks/session-end.sh`) wired into
  **`Brain-Eleven/.claude/settings.json`** — these already run the full
  pipeline plus graph rebuild, anomaly detection, and a same-day digest
  automatically, but **only when Claude Code's working directory is the
  Brain-Eleven repo itself**.

**The gap Phase 13 closes:** every memory in the vault so far is about
Brain-Eleven building itself. The system has never captured anything
from the user's actual work in *other* projects, because the hooks that
drive memory capture only fire inside this one repo.

**Full test suite passes and CI is green** as of commit `fc045dc`
(`pytest tests/` → 232 passed, coverage 84.73%, `.coveragerc` present).
Confirm this is still true before starting (`pytest tests/` from the
repo root) — if it isn't, something changed since this plan was written
and that regression should be understood before adding to it.

---

## 2. Goal

Let real decisions/lessons/open-loops from **any** project the user
works in end up in Brain-Eleven's memory store — safely, without
polluting the store with noise, and without leaking sensitive content
from other projects.

## 3. Explicit non-goals (do not build these now)

- **No passive full-transcript summarization.** Automatically reading
  an entire session transcript and extracting memories from it would
  need an LLM call (no API key is configured for this system — see
  `scripts/embedding-generator.py`'s fallback-embedding behavior, which
  is deliberate) and is a substantially bigger, riskier feature. This is
  "Phase 14" territory at earliest. Don't reach for it as a shortcut to
  hit this phase's goals faster.
- **Do not touch Docker/deployment.** Out of scope here.
- **Do not add real embeddings / OpenAI API key wiring.** Explicitly
  deferred by the user in an earlier conversation; unrelated to this
  phase.
- **Do not modify `scripts/search-api.py`'s existing endpoints** beyond
  what's specified in §5.3. It's tested (`tests/test_search_api.py`,
  35 tests) — don't regress it.

---

## 4. Three constraints found during planning (do not skip these)

These were found by *verifying* an earlier draft of this plan, not
assumed — check them yourself before relying on them further, but they
were true at planning time:

### 4.1 `~/.claude/settings.json` is a live, managed file — merge, never overwrite

Checked directly: `~/.claude/settings.json` (global, not per-project)
already exists and already contains:
- Working hooks under `SessionStart` (4 matcher blocks: `startup`,
  `resume`, `clear`, `compact`, each running `~/.claude/hooks/cbm-session-reminder`),
  plus a `PreToolUse` hook and a `SubagentStart` hook.
- A large `autoMode` block with `allow` / `soft_deny` / `environment`
  entries — including a carefully written security/trust-boundary
  policy for a **different, unrelated project** (`promtgen`), noting
  which of its files are secret-sensitive and that its GitHub repo is
  public.
- Plugin/marketplace config, statusline config, theme, etc.

**Implication:** any change to this file must be a surgical JSON merge
(read it, add only the new `SessionStart`/`SessionEnd`/whatever entries
needed for Brain-Eleven, write it back) — never a wholesale rewrite.
Losing the `cbm-*` hooks or the `promtgen` policy block would be a real
regression for the user's other work, invisible to any test in this
repo. If a settings-merge helper already exists somewhere in this
environment (check `~/.claude/hooks/`, `~/.claude/scripts/`, or ECC's
own tooling under `~/.claude/ecc/`), prefer it over hand-rolled JSON
surgery.

### 4.2 Proactive (unprompted) capture must be opt-in per project, default OFF

The original plan draft proposed "the assistant proactively writes
decisions to Brain-Eleven without asking, in every project." Rejected
after review: a project like `promtgen` has explicit, hand-written
notes about sensitive files and a public remote. Silently capturing
"decisions" while working there — even indirectly, even something that
seems harmless — could leak project-specific context into Brain-Eleven's
store, which sits under **`github.com/WinierKingYT/Brain-Eleven`, a
public repository.** `.claude/validated-memory.json` is currently
gitignored (verify: `git check-ignore .claude/validated-memory.json`
from the Brain-Eleven repo root should print the path), but that's one
gitignore mistake or one `git add -f` away from not protecting anything.

**Decision made:** proactive capture defaults to OFF everywhere. It only
activates in projects the user has explicitly opted into. See §5.2 for
the mechanism.

### 4.3 Schema gap: no way to tell which project a memory came from

`ValidatedMemory` (see `scripts/memory-validator.py`) has no field
recording which project/repo a memory originated in. Once memories can
come from anywhere, this becomes a real correctness problem, not just a
nice-to-have: a query like "did we decide to use Redis?" could surface
a decision from an unrelated project and present it as relevant. A
`project` field must be added (§5.1) before Phase 13's capture paths go
live, not after.

---

## 5. What to build

### 5.1 Schema: add a `project` field

**File:** `scripts/memory-validator.py`

Add a `project: str = ""` field to the `ValidatedMemory` dataclass
(alongside `source`, near the other CONTENT fields — see the class
around line 54 as of this writing). Update:

- `validate_single()` (around line 690) — add a `project: str = ""`
  parameter, thread it into the constructed `ValidatedMemory(...)`.
- `_merge_with_prior()` and `load_candidates()` — ensure `project` round-trips
  through the existing merge/carry-forward logic the same way `source_id`
  and other fields already do (read `mem.get("project", "")` when
  reconstructing carried-forward prior records — follow the existing
  pattern used for `resolution_note`, `superseded_by`, etc. in that
  function).
- `to_dict()` — no change needed, `asdict(self)` already includes every
  dataclass field automatically.

**Tests to add** (`tests/test_memory_validator.py`, alongside the
existing `TestSingleCandidateValidation` class): confirm `project` is
persisted through `validate_single()` → `append_validated()` →
re-read from disk, and that it survives being carried forward by
`_merge_with_prior()` on a second run where the memory isn't
re-submitted.

**Do not change `scripts/search-api.py`'s `MemoryCreate` Pydantic model
signature carelessly** — check `tests/test_search_api.py`'s
`test_create_memory_goes_through_real_validation` and
`test_create_memory_with_identical_content_dedupes` still pass after
adding an optional `project` field to that model too (default `""`,
backward compatible).

### 5.2 The opt-in list

**New file:** `.claude/remember-config.json` in the Brain-Eleven vault
(sits alongside `.claude/validated-memory.json`; gitignored the same
way — add the pattern to `.gitignore`, it's user-specific runtime
config, not source).

Shape:
```json
{
  "proactive_opt_in_projects": [
    "C:\\Users\\faruk\\Documents\\some-project-the-user-explicitly-allowed"
  ]
}
```

Absolute paths, exact string match against the current working
directory (or a normalized/resolved form of it — decide and document
which, then be consistent; Windows path casing/separator quirks are a
real footgun here, write a test for at least one path-normalization
edge case).

This file starts **empty** (`{"proactive_opt_in_projects": []}`) —
nothing is opted in by default, including Brain-Eleven's own repo
(explicit is better than assuming "the home project is obviously fine").

No CLI/UI is required to manage this list for Phase 13 — hand-editing
the JSON is an acceptable v1. If you want to add a small script
(`scripts/manage-opt-in.py` with `--add <path>` / `--remove <path>` /
`--list`) that's a reasonable, low-risk addition; keep it separate from
the core capture logic either way.

### 5.3 Capture mechanism (shared by both entry points below)

**New file:** `scripts/remember.py`

A thin wrapper around the *already-built and tested*
`MemoryValidator.validate_single()` / `append_validated()`
(`scripts/memory-validator.py`) — do not reimplement dedup/scoring/
conflict-detection, reuse what's there. Responsibilities:

1. Accept `type_`, `content`, `confidence`, `project` (the calling
   project's absolute path or a short identifier — decide which and
   document it; if using the full path, consider whether that leaks
   info via `validated-memory.json`'s content itself, e.g. a path that
   embeds a client name — this is exactly the kind of thing to flag
   back to the user rather than silently deciding).
2. Call `MemoryValidator(vault_path).validate_single(...)`, then
   `append_validated(...)` if `is_new` is `True`.
3. On success, trigger the same graph-rebuild step `search-api.py`'s
   `_rebuild_graph()` performs (`EntityExtractor(vault_path).build_graph()`)
   — reuse `scripts/entity_extractor.py`'s `EntityExtractor` directly;
   don't require the REST API server to be running (real usage was
   explicitly decided to not depend on Docker/the API being up
   continuously).
4. Expose both a Python function (importable) and a CLI entry point
   (`python remember.py --type decision --content "..." --project
   "..." --confidence 0.8`) — the CLI form is what a hook script or a
   slash-command implementation will actually shell out to.

**Tests:** `tests/test_remember.py` — mirror the existing
`TestSingleCandidateValidation` tests in `tests/test_memory_validator.py`
plus: dedup across two `remember.py` invocations for identical content
(same pattern as `test_validate_single_same_content_returns_existing_id_not_new_one`),
and a test confirming the graph is rebuilt after a successful call
(check via `KnowledgeGraph(vault_path).get_entity(new_memory_id)` is
not `None` afterward).

### 5.4 Entry point 1 — `/remember` (manual, works everywhere, no opt-in check)

A slash-command usable from **any** project session.

**Confirmed at planning time:** `~/.claude/commands/` exists and holds
markdown files (`aside.md`, `checkpoint.md`, `code-review.md`, etc.) —
this is the global custom-slash-command mechanism. Add
`~/.claude/commands/remember.md` following the same format as an
existing command in that directory (read 2-3 of them first to match
the expected frontmatter/structure exactly — don't guess the format).
Its implementation should shell out to
`python <brain-eleven-path>/scripts/remember.py` with the user's
`/remember` argument as `--content`, prompting for or inferring `--type`
and `--confidence` as appropriate (decide and document the default
`--confidence` if the user doesn't specify one — reusing
`validate_single()`'s existing default of `0.7` is reasonable).

`~/.claude/skills/` also exists (many skills present) as a fallback
pattern if the command-file approach turns out not to fit, but prefer
the commands directory — it's the more direct match for a `/remember`
invocation.

This path **ignores the opt-in list** entirely — the user explicitly
invoking `/remember` in any project is a deliberate action, not passive
capture, so §4.2's constraint doesn't apply to it.

**Acceptance test (manual, not pytest — this is a Claude Code UX
surface):** from a project other than Brain-Eleven, run `/remember`
with some content, then confirm it shows up in
`Brain-Eleven/.claude/validated-memory.json` with the correct `project`
field and a real ULID.

### 5.5 Entry point 2 — proactive capture (opt-in only)

This is a **behavioral** instruction for Claude (added to a hook or to
global guidance), not purely code: when working in a project that
appears in `remember-config.json`'s `proactive_opt_in_projects`, and a
real decision/lesson/open-loop is made during the session, call
`scripts/remember.py` (via §5.3) without asking first.

Concretely:
1. A `SessionEnd` hook entry added to `~/.claude/settings.json` (merged
   per §4.1) that runs a small script checking whether the current
   project's path is in the opt-in list; if not, no-op and exit 0
   immediately (fast, silent, no side effects — this is the safety
   gate, get this exactly right and test it in isolation).
2. If the project IS opted in, the actual "what counts as a decision
   worth capturing" judgment call happens in-session (this is
   Claude's own reasoning during the conversation, not a deterministic
   script) — document this clearly for whoever's implementing so they
   don't try to build a keyword-matching heuristic here. The
   SessionEnd hook's job is only the safety gate (§1 above) plus
   whatever housekeeping the existing Brain-Eleven SessionEnd hook
   already does when it fires from within Brain-Eleven itself — for a
   project other than Brain-Eleven, most of the existing
   `session-end.sh` logic (running `memory-compiler.py` against a
   `Daily.md` that doesn't exist there) doesn't apply and shouldn't run.

**Test:** a unit test for the opt-in-check script alone (given a
`remember-config.json` fixture and a candidate project path, assert
correct allow/deny), independent of any Claude Code hook plumbing that
can't be exercised by pytest.

---

## 6. Acceptance criteria for Phase 13 as a whole

- [ ] `pytest tests/` still passes in full (232+ existing tests, plus
      whatever this phase adds), coverage stays ≥ 80%
      (`.coveragerc` already excludes one-off scripts — decide whether
      `remember.py`'s CLI `__main__` block needs the same treatment,
      consistent with how other CLI scripts are handled).
- [ ] `flake8 scripts tests --select=E9,F63,F7,F82` stays clean.
- [ ] `~/.claude/settings.json`'s pre-existing `cbm-*` hooks, the
      `promtgen` `autoMode` policy, and every other pre-existing key
      are byte-for-byte unchanged except for the new Brain-Eleven
      hook entries added.
- [ ] `/remember` works from a non-Brain-Eleven project and produces a
      correctly-tagged (`project` field populated), deduped,
      quality-scored memory.
- [ ] Proactive capture does **not** fire in a project not on the
      opt-in list (test this explicitly, e.g. from `promtgen` or any
      other project not added to `remember-config.json`).
- [ ] `git check-ignore .claude/validated-memory.json` and
      `git check-ignore .claude/remember-config.json` both succeed from
      the Brain-Eleven repo root (i.e., neither is at risk of being
      committed to the public repo).
- [ ] A short README or doc update explaining: what `/remember` does,
      how to opt a project into proactive capture, and where to look
      (`remember-config.json`) to audit or revoke that.

## 7. Repo / environment facts (verify current before relying on)

- Repo root: `C:\Users\faruk\Documents\Brain-Eleven`
- GitHub remote: `https://github.com/WinierKingYT/Brain-Eleven.git`
  (**public**)
- Default branch: `master`
- No OpenAI API key configured (`.env`'s `OPENAI_API_KEY` is empty) —
  embeddings run on a deterministic fallback; irrelevant to this phase
  but don't accidentally require a key anywhere in new code.
- Python 3.13, dependencies in `requirements.txt` (note: `fastapi`
  was bumped to `0.115.6` and `httpx` pinned to `0.27.2` recently for
  TestClient compatibility — don't re-downgrade these).
- Existing hyphenated-filename modules (`memory-validator.py`,
  `memory-compiler.py`, etc.) are loaded via `importlib` in every
  consumer (`search-api.py`, `chat_interface.py`, test files) because a
  bare `import` can't handle hyphens in a filename — follow the same
  `_load_hyphenated_module` pattern (see `scripts/search-api.py` near
  its top) if `remember.py` needs to import from `memory-validator.py`
  directly rather than shelling out to it.
