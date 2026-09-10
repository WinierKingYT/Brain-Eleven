# Vault Hygiene Report

**Date:** 2026-09-10
**Scope:** Vault content hygiene only; no IG package, retrieval, extraction, V2, or Phase 20 implementation was changed.
**Review status:** Ready for Claude/Ahmet independent review. No self-declared completion or `SHIP` verdict.

## File movement

No file was deleted. Every relocation below used `git mv` and preserves the original file content and history.

| Source | Destination | Count | Rule |
|---|---|---:|---|
| `🗂️ Proje Notları/Kararlar/` | `🗂️ Proje Notları/Referans/` | 95 | General, date-free technical/reference notes identified by the agreed `agent-skills`, `ai-engineering`, `archify`, `github-harvest`, `gpt-image`, and `hamle*` families. |
| `🗂️ Proje Notları/Dersler/` | `🗂️ Proje Notları/Referans/` | 8 | General `agent-skills`, `ai-engineering`, and `github-harvest-lesson-*` notes under the same rule. |
| **Total moved** |  | **103** |  |

`Kararlar/` retains the six date-named decisions, 15 project-specific `minecraftmcp` decisions, five `petsistemi` decisions, the `promackro` project decision, three product/method decisions, four `INDEX-*` hubs, the `Kararlar.md` hub, and the ambiguous manifest listed below. `Dersler/` retains the ten project-derived or experience-derived lessons and its hub.

### Ambiguous and intentionally untouched

- `🗂️ Proje Notları/Kararlar/minecraftmcp_bulk_000[4-9].md` — this file is a bare slug list without a decision body. It was not moved; Ahmet should decide whether it is an index/manifest or discardable source material.
- `INDEX-*.md` files were not edited or moved.

## Link cleanup

- Replaced `[[Beyin]]` with `[[🧠 Brain-Eleven]]` in `Proje Envanteri.md`, `Dersler/Dersler.md`, and `Kararlar/Kararlar.md`.
- Removed the nonexistent `[[ŞABLON - Ders]]` and `[[ŞABLON - Karar]]` references from the two hubs.
- Removed one additional stale `[[ŞABLON - Karar]]` occurrence from the methodology note after the same missing target was found there.
- Added explicit `🗂️ Proje Notları/Referans/...` links to both hubs so moved records remain discoverable.

## Companion refresh

- `🔮 Companion/Açık Döngüler.md` now separates current open work from the retained, historical Hamle 7 and mem0 blocks. It records the GitHub branch deletion question for Ahmet, open remote CI/native-trust follow-ups for B1/B2, the unselected next IG-04 subpackage, and pending B2 independent review.
- `🔮 Companion/Threads.md` now has a one-line git-history timeline from IG-00 through IG-04 B2 and labels the pre-IG thread records as historical.
- `🔮 Companion/Last Session.md` now records the 2026-09-10 branch synchronization, B1/B2 status, and this vault assessment while retaining the 2026-08-28 entry as history.
- `🔮 Companion/Daily.md` has a factual 2026-09-10 entry based on the recorded commits, test evidence, and this session.

## Validation

- The three requested hub notes now use the real Brain-Eleven hub, and the missing template targets were removed from the operational notes.
- Move count is 103; destination `Referans/` contains 103 files.
- No source file was deleted; the ambiguous manifest and all `INDEX-*` files remain in place.
- Existing user evidence/temp files were not staged, changed, or removed.

## Open review questions

1. Ahmet must confirm the deletion state of the six old GitHub branches.
2. Claude/Ahmet must independently review this vault change set; this report does not declare it complete or shipped.
