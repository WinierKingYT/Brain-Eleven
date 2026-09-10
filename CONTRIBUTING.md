# Contributing

## Setup

```bash
pip install -r requirements.txt
pip install pytest   # test runner is not pinned in requirements.txt
cp .env.example .env # fill in OPENAI_API_KEY if you need real embeddings
```

## Running checks

```bash
python -m pytest tests -m "not integration and not graduation" -q   # fast suite
python -m pytest tests -m "integration or graduation" -q            # slower suite
python -m evals.baseline_snapshot --baseline baseline-v3 --check    # eval regression gate
flake8 --select=E9,F63,F7,F82 .                                     # critical lint only
```

Run the fast suite and the baseline snapshot check before every push. A push
that turns CI red costs more than the minute it takes to run these first.

## Branch and phase discipline

This project's biggest recurring failure has not been code quality — it has
been **work happening on branches that never get merged back**, while
`master` and its status docs silently fall behind. On 2026-09-10, `master`
was found frozen at an old "IG-00 in progress" commit while 91 unmerged
commits of real, already-closed work sat across five sequential branches.
Concretely:

1. **One active branch at a time per line of work.** If you're picking up
   where another branch left off, merge or fast-forward it into `master`
   *before* starting new work on top of it — don't branch off an unmerged
   branch "to keep going."
2. **Don't open the next package/phase before the current one is merged to
   `master` and its status doc says so.** `PROJECT-STATUS.md` and
   `DOCUMENTATION-AUTHORITY.md` describe which package is active; if you're
   about to start the next one and that file doesn't say the previous one
   shipped, stop and merge first.
3. **A "SHIP" or "independent review" verdict written by the same
   session/branch that did the work is not independent.** Real independent
   review means a separate pass — re-run the claimed checks yourself, don't
   just read the report and trust the numbers. (This project has caught real
   discrepancies this way — see `IG-00-INDEPENDENT-REVIEW.md`.)
4. **Delete a branch once it's merged.** A merged, undeleted branch is how
   this project ended up with six stale branches pointing at superseded
   history.

## Roles: Claude vs. Codex

Default split (cost-driven — Claude is the pricier of the two): **Claude
manages, Codex executes.** As of 2026-09-10, Ahmet delegated project
management to Claude — current status, documentation, quality bar, and
product vision/direction for Brain-Eleven are Claude's ownership, not just
"planning." Claude decides what the next bounded package is, writes its
contract, and gives Codex the instructions to implement it. Codex writes the
code, tests, and other implementation work, and does not set direction on its
own initiative — if Codex's own evidence (e.g. a probe result) suggests a
new direction, that goes back to Claude to turn into a contract, not straight
into implementation.

Claude has no direct connection to Codex in this environment; Ahmet relays
messages between the two sessions. Ahmet still makes the call on anything
this project's own contracts mark as a required human checkpoint (see each
`IGxx-*-CONTRACT.md`'s own approval clause) — Claude does not self-approve
those on Ahmet's behalf.

This is a default, not a hard boundary; either can do either when it makes
sense. Whoever is doing hands-on work in a given session still follows the
branch/`NEXT.md` discipline above — the role split doesn't relax it.

## Documentation

- End a work session by updating `NEXT.md` (a few lines: what changed, what's
  next) — that's the file meant to answer "where are we" without reading
  `PROJECT-STATUS.md`'s evidence ledger.
- New package contracts/reports (`IGxx-*.md`) get an entry in
  `DOCUMENTATION-AUTHORITY.md`'s override table — an unregistered doc
  defaults to HISTORICAL and shouldn't be treated as current guidance.
- Don't create a new top-level status document if `PROJECT-STATUS.md` can be
  updated instead. The number of root-level `.md` files is a standing
  problem, not a pattern to continue.
- Superseded phase/plan docs move to `docs/history/`, not deletion.
