# W-13 Project Root / Project ID Package Report

PACKAGE: W-13  
REVISION: `cc344e393331b6f47c7ff221ad41ee75fce4538b`

## Objective

Reject a capture/API request when an explicit `project_id` does not match the
registered identity of the supplied `project_root`, without adding a second
canonical write authority or changing root-only relocation behavior.

## Files changed

- `scripts/memory_scope.py`: shared `resolve_capture_scope()` boundary now
  reads the registry before accepting a root+ID pair, rejects mismatches and
  unregistered explicit IDs, and preserves root-only auto-registration.
- `tests/test_w13_project_root_id_scope.py`: direct resolver, remember,
  registry side-effect, relocation, global-scope, and FastAPI create coverage.
- `WEAKNESS-W13-PROJECT-ROOT-ID-CONTRACT.md`: bounded contract.
- `WEAKNESS-W13-PROJECT-ROOT-ID-PACKAGE-REPORT.md`: this evidence record.

No `MemoryStore`, `ProjectRegistry`, `MemoryValidator`, graph, retrieval,
V2, or Phase 20 implementation was changed.

## Root cause addressed

The old resolver called `registered_project_identity(root)` but retained a
caller-supplied ID whenever it was non-empty. This allowed root A's label to be
stored under root B's opaque namespace. The new path uses a read-only registry
lookup for explicit IDs, rejects `PROJECT_ROOT_ID_MISMATCH` or
`PROJECT_ROOT_ID_UNREGISTERED`, and only uses the existing registering path
for root-only calls.

## Tests added

- mismatched registered root/ID fails closed and leaves registry revision/data
  unchanged;
- matching root/ID succeeds;
- unregistered root + explicit ID rejects without creating the registry file;
- root-only auto-registration and relocation preserve identity;
- global project metadata rejection and root-only CLI compatibility;
- `remember()` rejects before canonical memory creation;
- `/memories` maps the mismatch to HTTP 422 and writes no record.

## Tests executed

- Pre-fix focused baseline: expected red — 4 mismatch/API cases failed.
- W-13 focused: **8 passed, 2 warnings**.
- Scope/capture/API/regression set: **156 passed, 2 warnings**.
- Full suite at exact revision: **1189 passed, 2 warnings**.
- Critical flake8 (`E9,F63,F7,F82`): PASS.
- compileall: PASS.
- `git diff --check`: PASS.

## Safety metrics

- Rejected root/ID mismatch: no registry revision change; no canonical file;
  no graph rebuild.
- Wrong-project leakage in new direct/API cases: 0.
- Existing relocation and two-project same-content isolation: PASS.
- Canonical transaction and lock semantics: unchanged.
- Phase 20: `FROZEN / LOCKED`.
- V2: `SHADOW`.

## Known limitations

- Existing records written before this fix are not automatically reclassified;
  remediation would require a separate bounded package.
- The resolver still lives in the legacy `scripts/memory_scope.py` authority
  behind the existing package re-export; migration of that implementation is
  outside W-13.
- The full suite reports the repository's existing two deprecation warnings.

## Open failures

- Independent implementation review is pending.
- W-07B remains `FIX-FIRST / NOT ACCEPTED`.
- W-12A (the analogous `authority/cache.py` race) remains open.
- W-14 through W-18 remain audit findings; no work on them is implied here.

## Independent review

Contract review: **SHIP** by an independent read-only reviewer after contract
revision `4311b1f`. Implementation review: **SHIP** at exact code revision
`cc344e3` with current test/documentation head `366835b`. The reviewer reran
103 focused tests (2 inherited dependency warnings), critical flake8,
compileall, and diff checks. It verified the read-only registry lookup,
fail-closed mismatch/unregistered behavior, root-only relocation, global CLI
compatibility, remember/API no-write behavior, and project isolation. No new
P0/P1/P2 finding was reported.

SCORE BEFORE: scope/fail-closed safety 6.5/10  
SCORE AFTER: scope/fail-closed safety 7.5/10 (W-14/W-17 remain open)

VERDICT: **SHIP**

