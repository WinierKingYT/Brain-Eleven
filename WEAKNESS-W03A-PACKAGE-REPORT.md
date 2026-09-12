# W-03A Package Report — Transcript Path Confinement

**PACKAGE:** W-03A / native transcript path confinement  
**REVISION:** a6f7fd1  
**OBJECTIVE:** Prevent native capture from queueing or reading a transcript
outside the trusted Claude/Codex transcript roots.

## Files changed

- `scripts/capture_provenance.py` — canonical root resolver and content-free
  error codes.
- `brain_eleven/runtime/worker.py` — provenance validation before enqueue
  `stat`/queue write and immediately before worker evidence read.
- `tests/test_capture_provenance.py` — root, traversal, client, symlink,
  enqueue side-effect and worker revalidation tests.
- Runtime test fixtures now declare explicit temporary transcript roots; no
  production authority or transcript content behavior is changed by fixtures.

## Root cause addressed

The old boundary accepted any absolute regular file after generic path checks.
It did not prove that a hook-provided locator belonged to the native client
transcript root. A malicious or stale locator could therefore make the worker
read an unrelated local file.

## Behavior and safety

- Client identity is taken from the trusted runtime argument.
- Roots are explicit `transcript_roots` configuration when present, otherwise
  native local Claude/Codex roots.
- Absolute path, parent traversal, source symlink, regular-file and resolved
  root containment checks fail closed.
- Enqueue rejection happens before queue/evidence/canonical effects.
- Worker revalidates after queueing, so root/config changes cannot turn a
  previously accepted locator into a readable source.
- Missing-source compatibility remains `TRANSCRIPT_NOT_FOUND`; other
  provenance failures use bounded `TRANSCRIPT_PROVENANCE_*` codes.

## Tests executed

- W-03A + affected capture/runtime suite: **99 passed, 2 warnings**.
- Full suite: **969 passed, 2 warnings**.
- Critical flake8 (`E9,F63,F7,F82`): **PASS**.
- `compileall`: **PASS**.
- `git diff --check`: **PASS**.

## Quality metrics

**BEFORE:** Transcript locator was only checked for absolute/local-file
properties; client-root confinement was absent.  
**AFTER:** Root confinement is enforced at enqueue and worker read boundaries;
foreign-root and symlink inputs have focused evidence.  
**Scope score:** 6.0 → 7.0 provisional.  
**Capture score:** 8.0 → 8.0 provisional; W-04 late transcript loss and W-05
prompt-event semantics remain open.

## Known limitations / deferred work

W-03A is intentionally not full transcript provenance. It does not prove
Claude project-slug ownership, Codex project association, session metadata
ownership, same-size replacement identity, late transcript durability, or
prompt-event semantics. Those remain separate bounded packages and must not be
hidden by this report.

## Independent review

Required and pending. The reviewer must inspect the contract, exact revision,
tests, full regression and deferred boundaries, then return exactly `SHIP`,
`FIX-FIRST` or `RETHINK`. Self-review is not acceptance.

**VERDICT:** REVIEW PENDING
