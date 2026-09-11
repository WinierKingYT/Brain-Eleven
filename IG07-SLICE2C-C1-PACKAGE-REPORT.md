# IG-07 Slice 2C — C1 Package Report

**PACKAGE:** IG-07 / Slice 2C / C1 — dedupe validated memory
**REVISION:** `d39a15b` (tests) on top of `66bec10` (implementation)
**OBJECTIVE:** `scripts/dedupe-validated-memory.py` içindeki duplicate planning/apply CLI'sini canonical `brain_eleven.lifecycle.dedupe` package yüzeyine taşımak; legacy script'i thin adapter yapmak; canonical yazma, CAS ve lifecycle davranışını korumak.

## FILES CHANGED

- `brain_eleven/lifecycle/dedupe.py` — `SUPERSESSION_NOTE`, `plan_dedupe` ve `main` canonical implementation.
- `brain_eleven/lifecycle/__init__.py` — package exports (`plan_dedupe`, `dedupe_main`, note constant).
- `scripts/dedupe-validated-memory.py` — cached package loader, compatibility exports and direct CLI adapter.
- `tests/test_lifecycle_dedupe.py` — C1 identity, adapter, tie-break, idempotence, CAS, backup, dry-run and integrity tests.

`MemoryLifecycleManager`, `MemoryStore`, `migrate-legacy-memory.py`, `migrate-memory-scope.py` ve Phase 20 production yolları değiştirilmedi.

## ROOT CAUSES ADDRESSED

- Dedupe planner'ın implementation authority'si hyphenated script'te kalıyordu.
- Equal timestamp kayıtlarında winner seçimi persisted list order'a bağlıydı.
- Legacy direct import/CLI ile package surface arasında canonical identity kanıtı yoktu.
- Dedupe apply/replay, stale snapshot, dry-run ve backup davranışları için bounded regression kanıtı yoktu.

## BEHAVIOR CHANGE

Canonical winner sıralaması artık:

```python
(timestamp, memory_id)
```

şeklindedir. İlk anahtar aynı olduğunda daha küçük `memory_id` canonical seçilir. Superseded kayıtlar hâlâ active cluster'a alınmaz. Başka bir lifecycle veya persistence davranışı değiştirilmedi.

## WRITE PATH / AUTHORITY

`main --apply` yalnızca `MemoryLifecycleManager.supersede_memory` çağrılarını planlar ve `manager.save()` çağırır. `save()` mevcut lifecycle manager üzerinden `MemoryStore.replace(..., expected_revision=store_revision)` kullanır. Lock, CAS, revision increment, fixed backup ve atomic temp-file write hâlâ canonical `MemoryStore` implementasyonundadır; dedupe package'ı doğrudan JSON yazmaz.

## TESTS ADDED

`tests/test_lifecycle_dedupe.py` içinde 7 test:

- package/adapter/bare-module object identity;
- adapter-only AST ve duplicate implementation kontrolü;
- equal-timestamp deterministic winner ve already-superseded koruması;
- apply replay idempotence ve ikinci çalıştırmada `save()` çağrılmaması;
- stale snapshot sonrası `MemoryStoreConflict` ve sessiz overwrite olmaması;
- dry-run canonical effect üretmemesi ve apply sonrası fixed backup;
- record count/ID set bütünlüğü.

## TESTS EXECUTED

- Focused lifecycle + C1 + PRE-12 suite: **50 passed**.
- Full suite: **920 passed, 2 warnings** in `175.70s`.
- Critical flake8: `E9,F63,F7,F82` — **PASS**.
- `compileall` — **PASS**.
- Clean import/identity sanity — **PASS**.
- `git diff --check` — **PASS**.

Warnings mevcut FastAPI/Starlette dependency deprecation uyarılarıdır; C1 değişikliklerinden kaynaklanan failure yoktur.

## SAFETY / INTEGRITY METRICS

- Canonical write path bypass: **0**.
- Direct JSON write in dedupe adapter/package: **0**.
- Duplicate canonical record deletion: **0**; records yalnız lifecycle status/link alanlarıyla güncellenir.
- Stale snapshot silent overwrite: **0** (explicit `MemoryStoreConflict`).
- Dry-run canonical effect: **0**.
- Equal-timestamp winner: deterministic and test-covered.
- Cross-project behavior: dedupe fingerprint semantics mevcut script ile aynı tutuldu; C1 yeni scope rule eklemedi.

## KNOWN LIMITATIONS

- `MemoryLifecycleManager` hâlâ legacy `scripts/memory-lifecycle.py` implementation'ını package bridge üzerinden kullanıyor; bu C1 kapsamı dışındadır.
- Dedupe için production/behavioral caller sayısı hâlâ sıfırdır; C0 retain-and-migrate kararı bu package için kaydedilmiş olsa da gerçek dogfood kullanım kanıtı değildir.
- Dedupe planında eksik `memory_id` alanı mevcut legacy davranışta olduğu gibi `KeyError` üretir; schema repair bu paketin görevi değildir.
- C1, `migrate-legacy-memory.py` ve `migrate-memory-scope.py` migration yüzeylerini açmaz.

## OPEN FAILURES / P0 / P1

- Açık C1 P0: **yok**.
- Açık C1 P1: **yok**.
- Independent review: **bekliyor**.

## INDEPENDENT REVIEW

**SHIP**, recorded 2026-09-12. See `IG07-SLICE2C-C1-INDEPENDENT-REVIEW.md` —
idempotence, CAS-conflict, dry-run, and integrity tests independently
re-read and re-run (each test confirmed to prove the claimed property, not
just assert a trivial outcome); full suite reproduced at 920 passed;
`migrate-legacy-memory.py`, `migrate-memory-scope.py`, `MemoryStore`, and
`MemoryLifecycleManager` confirmed untouched by diff.

## SCORE BEFORE / AFTER

- C1 öncesi dedupe package authority: **legacy script / unverified safety contract**.
- C1 sonrası: **package implementation + compatibility adapter; focused safety evidence green**.
- Genel IG score değişikliği yapılmadı; independent review ve C1 kabulü bekleniyor.

## VERDICT

**ACCEPTED.** C1 kapalı. C3 (`migrate-memory-scope.py` + rollback) kendi
bounded contract'ı ile açılabilir; `migrate-legacy-memory.py` C0 kararı
gereği bu slice'ın dışında kalmaya devam eder.
