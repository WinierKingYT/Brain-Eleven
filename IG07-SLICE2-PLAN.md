# IG-07 Slice 2 Planı

**Durum:** PLAN ONLY — üretim implementasyonu başlatılmadı  
**Kapsam:** Orta risk grubundaki 12 modülün (task state context hariç 11 modül) envanteri, hedef package sınırları, risk sınıfları ve ilk alt-dilim önerisi.

## Envanter yöntemi

Caller sayısı, hedef scriptin kendi tanımı dışındaki Python dosyalarında gerçek import, dynamic loader veya çalışma zamanı referansı bulunan **benzersiz dosya** sayısıdır. Yorumlar, docstring'ler ve yalnızca migration envanteri için tutulan string listeleri caller sayısına dahil edilmedi. `conftest.py` içindeki legacy alias kayıtları test altyapısı olarak ayrıca not edildi.

LOC değerleri mevcut `scripts/` dosyasının fiziksel ve boş olmayan satır sayılarıdır. Son değişiklik tarihi `git log -1` çıktısından alınmıştır.

## Package hedefleri ve mevcut köprüler

| Legacy modül | Mevcut köprü / gerçek durum | Önerilen canonical hedef | Üretim caller / test caller | LOC (fiziksel / boş olmayan) | Son değişiklik | Risk |
|---|---|---|---:|---:|---|---|
| `chat_interface.py` | Köprü yok; `search-api.py` bare import ile kullanıyor. | `brain_eleven/runtime/chat_interface.py` | 1 / 1 | 403 / 346 | 2026-09-09 | MEDIUM |
| `dedupe-validated-memory.py` | Köprü yok; `brain_eleven.lifecycle` yalnız lifecycle manager sağlar. | `brain_eleven/lifecycle/dedupe.py` | 0 / 0 | 112 / 91 | 2026-09-06 | HIGH |
| `entity_extractor.py` | `brain_eleven/extraction/__init__.py`, scriptteki nesneleri yeniden export ediyor. | `brain_eleven/extraction/entities.py` ve `extraction/__init__.py` export'u | 2 / 5 | 306 / 260 | 2026-09-09 | HIGH |
| `install-cross-project-memory.py` | Doğrudan köprü yok; ayrı ve daha yeni `brain_eleven/runtime/install.py` yüzeyi var. İki implementasyon önce karşılaştırılmalı. | Mevcut `brain_eleven/runtime/install.py` içinde tek installer authority | 0 / 1 | 371 / 318 | 2026-09-02 | HIGH |
| `knowledge_graph.py` | `brain_eleven/graph/projection.py` script nesnelerini yeniden export ediyor. | `brain_eleven/graph/projection.py` içinde canonical projection implementasyonu | 2 / 5 | 394 / 340 | 2026-09-09 | HIGH |
| `memory_provenance.py` | Köprü yok; ayrı provenance projection ve kendi test yüzeyi var. | `brain_eleven/memory/provenance.py` | 0 / 1 | 192 / 156 | 2026-09-09 | LOW |
| `migrate-legacy-memory.py` | Köprü yok; açıkça çalıştırılan one-off migration CLI. | `brain_eleven/memory/migrations.py` (`migrate_legacy_memory`) | 0 / 0 | 93 / 72 | 2026-09-06 | HIGH |
| `migrate-memory-scope.py` | Köprü yok; bağımsız scope-v2 migration/rollback CLI. | `brain_eleven/memory/migrations.py` (`migrate_scope` ve rollback yüzeyi) | 0 / 2 | 251 / 212 | 2026-09-06 | HIGH |
| `post_session_maintenance.py` | Köprü yok; package support/extraction/memory kullanıyor, fakat session pipeline script yolunu çalıştırıyor. | `brain_eleven/runtime/maintenance.py` | 1 / 2 | 154 / 124 | 2026-09-06 | MEDIUM |
| `remember.py` | Köprü yok; manual capture ve project registry ile canonical yazım yoluna bağlı. | `brain_eleven/memory/capture.py` | 1 / 2 | 219 / 182 | 2026-09-06 | HIGH |
| `task_model.py` | Köprü yok; task state context, authority serialization ve evaluation yüzeyleri doğrudan scripti import ediyor. | `brain_eleven/runtime/task.py` | 3 / 2 | 668 / 577 | 2026-09-09 | HIGH |
| `task_state_context.py` | `brain_eleven/runtime/context.py` import ediyor; 26/26 caller ile en geniş blast radius. | `brain_eleven/runtime/context.py` | **26 / 26** | 101 / 83 | 2026-09-09 | **EXCLUDED** |

### Caller kanıtı

- `chat_interface.py`: `scripts/search-api.py`; testte `tests/test_phase11_graph_chat.py`; `conftest.py` yalnız test alias'ıdır.
- `dedupe-validated-memory.py`: production caller yok; migration contract testinde yalnız dosya envanteri var.
- `entity_extractor.py`: `brain_eleven/extraction/__init__.py` bridge ve `scripts/remember.py` dynamic loader; doğrudan test yüzeyi `test_graph_projection_revision.py`, `test_memory_backup.py`, `test_phase11_graph_chat.py`, `test_phase14_graduation_failures.py`, `test_phase14_scope.py`.
- `install-cross-project-memory.py`: production caller yok; installer senaryoları `tests/test_phase14_scope.py` içinde.
- `knowledge_graph.py`: `brain_eleven/graph/projection.py` bridge ve `scripts/entity_extractor.py`; doğrudan test yüzeyi `test_phase14_scope.py`, `test_graph_projection_revision.py`, `test_phase11_graph_chat.py`, `test_phase14_graduation_failures.py`, `test_remember.py`.
- `memory_provenance.py`: production caller yok; `tests/test_memory_provenance.py` ve migration contract testindeki compatibility listesi.
- `migrate-legacy-memory.py`: production caller yok; migration contract listesi dışında behavioral test yok.
- `migrate-memory-scope.py`: `tests/test_memory_scope_migration.py` ve `tests/test_phase14_scope.py` tarafından loader ile çalıştırılıyor.
- `post_session_maintenance.py`: `scripts/session_pipeline.py` subprocess caller; `tests/test_post_session_maintenance.py` ve `tests/test_session_pipeline.py`.
- `remember.py`: `scripts/remember_opt_in.py`; `tests/test_remember.py` ve `tests/test_capture_safety.py`.
- `task_model.py`: `scripts/task_state_context.py`, `authority/serialization.py`, `evals/task_state_eval.py`; task model, project-caller ve context-coverage testleri.

## Risk sınıflandırması

### LOW

`memory_provenance.py` en düşük riskli modüldür: runtime production caller'ı yoktur, canonical `MemoryStore` yalnız okunur ve yazılan dosya ayrı bir provenance projection'ıdır. Yine de lock, corruption ve revision davranışı korunmalıdır.

### MEDIUM

`chat_interface.py` read-only, fakat search, graph, summarizer ve anomaly yüzeylerini aynı orchestration sınıfında birleştirir. `post_session_maintenance.py` session-end hook zincirindedir; hata yutmama, idempotence ve rapor üretimi nedeniyle caller sayısı düşük olsa da runtime etkisi vardır.

### HIGH

`dedupe-validated-memory.py`, `migrate-legacy-memory.py`, `migrate-memory-scope.py` ve `remember.py` canonical memory/lifecycle yazımına veya veri dönüşümüne dokunur. `entity_extractor.py` ve `knowledge_graph.py` revision-bound graph projection üretir. `install-cross-project-memory.py` canlı Claude/Codex ayarlarını değiştirir. `task_model.py` geniş authority/evaluation blast radius'una sahiptir. Bu modüller için önce ayrı bounded contract ve rollback/parity kanıtı gerekir.

`task_state_context.py` bu slice'a alınmaz; mevcut envanterdeki 26/26 caller nedeniyle ayrı bir migration planı gerektirir.

## İlk alt-dilim önerisi

İlk alt-dilim üç modülden oluşmalıdır. Bunların birbirleriyle doğrudan import bağı yoktur ve kalanlar içinde en düşük caller/risk bileşimine sahiptir:

### 1. `memory_provenance.py`

- **Hedef:** `brain_eleven/memory/provenance.py`
- **Neden:** 0 production caller, ayrı projection dosyası, mevcut 2 behavioral test.
- **Mevcut testler:** `tests/test_memory_provenance.py` (2 test); `tests/test_pre12_memory_state_caller_migration.py` compatibility/authority kontrolleri.
- **Uygulama sınırı:** sınıf ve serialization davranışını package içine taşı; scripti direct-execution/compatibility adapter yap; `MemoryStore` authority'sine yazma ekleme.
- **Regresyon kanıtı:** package/legacy object identity, corruption/lock error parity, revision-bound provenance read/write ve CLI smoke.
- **Tahmini diff:** yaklaşık **220–260 değişen satır** (192 satır implementasyon taşınması, adapter, export ve parity testleri).

### 2. `chat_interface.py`

- **Hedef:** `brain_eleven/runtime/chat_interface.py`
- **Neden:** yalnız bir production import caller'ı var; modül read-only cevap üretir ve doğrudan canonical write yapmaz.
- **Mevcut testler:** `tests/test_phase11_graph_chat.py` (43 test); `scripts/search-api.py` import/parity yolu; migration caller contract kontrolleri.
- **Uygulama sınırı:** `Intent`, `ConversationContext`, `ChatAgent` ve handler'ları package içine taşı; search/graph/support package yüzeylerini koru; `handle_create` doğrulama pipeline'ını bypass etmemeli.
- **Regresyon kanıtı:** legacy/package/bare import object identity, tüm intent sınıflandırma ve handler testleri, project scope izolasyonu, direct CLI parity.
- **Tahmini diff:** yaklaşık **450–550 değişen satır** (403 satır implementasyon, thin adapter, export ve import/parity testleri).

### 3. `post_session_maintenance.py`

- **Hedef:** `brain_eleven/runtime/maintenance.py`
- **Neden:** tek production subprocess caller'ı var; işlev session-end raporu üretimiyle sınırlı ve mevcut support/extraction package'larına bağlanıyor.
- **Mevcut testler:** `tests/test_post_session_maintenance.py` (13 test), `tests/test_session_pipeline.py` (4 test), migration caller contract kontrolleri.
- **Uygulama sınırı:** `_run_step`, `run_maintenance`, `save_report`, `summarize_for_shell` ve CLI'ı taşı; session pipeline komut satırı ve `--quiet`/`--generated-by-run` davranışlarını koru; hook bütçesini genişletme.
- **Regresyon kanıtı:** package/legacy identity, step failure isolation, idempotent report, session pipeline subprocess arguments ve direct CLI parity.
- **Tahmini diff:** yaklaşık **180–230 değişen satır** (154 satır implementasyon, adapter, export ve parity testleri).

Bu üçlü tamamlanıp bağımsız review ile kabul edilmeden HIGH riskli migration, installer, graph/extraction, manual capture veya task model modüllerine geçilmemeli. Dördüncü modül eklenmesi gerekirse `install-cross-project-memory.py` caller sayısı düşük olsa da canlı client configuration mutasyonu nedeniyle bu alt-dilime alınmamalıdır.

## Sonraki bounded dilimler

Önerilen sıra:

1. **Slice 2A:** `memory_provenance.py`, `chat_interface.py`, `post_session_maintenance.py`.
2. **Slice 2B:** `entity_extractor.py` ve `knowledge_graph.py`; mevcut bridge'ler gerçek implementation authority'ye dönüştürülür, graph projection revision testleri genişletilir.
3. **Slice 2C:** `dedupe-validated-memory.py`, `migrate-legacy-memory.py`, `migrate-memory-scope.py`; migration/rollback ve canonical write kanıtları ayrı tutulur.
4. **Slice 2D:** `install-cross-project-memory.py` ve `remember.py`; canlı config ve canonical capture güvenlik review'su gerekir.
5. **Slice 2E:** `task_model.py`; ancak caller inventory güncellendikten ve ayrı task-state planı hazırlandıktan sonra.
6. **Ayrı çalışma:** `task_state_context.py`; 26/26 caller nedeniyle Slice 2 kapsamı dışında.

Her alt-dilim için implementasyon öncesi bounded contract, focused tests, full regression ve bağımsız review gereklidir. Bu doküman hiçbir production dosyasını değiştirmez ve implementasyon onayı vermez.

