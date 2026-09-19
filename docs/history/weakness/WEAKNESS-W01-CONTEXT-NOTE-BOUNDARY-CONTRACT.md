# W-01 Contract — V1 Context Related-Note Boundary

**Status:** BOUNDED CONTRACT / IMPLEMENTATION AUTHORIZED BY ENGINEERING GOAL  
**Priority:** P1 safety  
**Target:** `scripts/context-compiler.py` related-note reader  
**Phase 20:** FROZEN / LOCKED

## Problem

The V1 compiler reads each `related_notes` value by concatenating it with the
configured notes directory. The value is memory-derived input and is not a
trusted filesystem path. A traversal value can make bootstrap context read a
file outside the vault notes boundary.

## Scope

The package may change only the V1 related-note resolution/read boundary and
its focused tests. It must:

1. resolve each candidate from the configured notes directory;
2. accept only a single note basename in the existing `.md` representation;
3. reject traversal, absolute paths, alternate separators and symlink escapes;
4. keep missing/invalid links invisible in the returned related-note map;
5. preserve the existing first-200-character projection and ordering;
6. preserve wikilink fallback behavior for valid in-bound note names.

Containment must be checked after `resolve()` and before opening the file. The
implementation should remain compatible with the supported Windows and Linux
path semantics.

## Out of scope

No ranking changes, task-aware retrieval, V2 promotion, raw markdown redesign,
canonical MemoryStore schema change, hook change, Phase 20 work, or unrelated
refactor is allowed in this package.

## Acceptance evidence

- traversal (`../`, `..\\`, absolute and mixed-separator) never reads outside
  the notes directory;
- a symlink inside the notes directory pointing outside is rejected;
- an ordinary in-bound note still produces the same truncated projection;
- missing and malformed links remain bounded misses rather than exceptions;
- existing `tests/test_context_compiler.py` and scope/privacy tests pass without
  modification;
- a new focused test proves the boundary using a real temporary filesystem;
- adapter/import and direct CLI behavior remain unchanged;
- full suite, critical flake8 (`E9,F63,F7,F82`), compile sanity and
  `git diff --check` pass;
- an independent read-only reviewer returns only `SHIP`, `FIX-FIRST` or
  `RETHINK`.

## Package report fields

`PACKAGE`, `REVISION`, `OBJECTIVE`, `FILES CHANGED`, `ROOT CAUSES ADDRESSED`,
`TESTS ADDED`, `TESTS EXECUTED`, `QUALITY METRICS BEFORE/AFTER`, `SAFETY
METRICS`, `KNOWN LIMITATIONS`, `OPEN FAILURES`, `INDEPENDENT REVIEW`, `SCORE
BEFORE/AFTER`, `VERDICT`.
