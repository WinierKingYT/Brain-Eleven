# Brain-Eleven

Local, privacy-first second-brain system: a revisioned canonical memory store,
project-scoped state, safe retrieval, and a non-injecting context compiler,
wired into Claude/Codex via hooks so context loads automatically at session
start.

## Quickstart

```bash
pip install -r requirements.txt
pip install pytest  # not in requirements.txt; needed to run tests locally
python -m pytest tests -m "not integration and not graduation" -q
```

Or via Docker: `make build && make up && make health`.

Copy `.env.example` to `.env` before running anything that touches embeddings
or the API — see that file for what each variable does and what happens when
it's left unset (semantic search and API auth both degrade safely, they don't
fail open).

## Where to go next

| You want to... | Read |
|---|---|
| Understand how the pieces fit together | `ARCHITECTURE.md` |
| Set up your environment, run tests, open a PR | `CONTRIBUTING.md` |
| Know where we are and what's next, in plain language | `NEXT.md` |
| Know what's actually done vs. in progress, with evidence | `PROJECT-STATUS.md` |
| Know which other `.md` file to trust | `DOCUMENTATION-AUTHORITY.md` |

Older `IG*`, `PHASE*`, `PRE*` files are package-level contracts and closure
reports, not entry points — `PROJECT-STATUS.md` tells you which one is
currently active.
