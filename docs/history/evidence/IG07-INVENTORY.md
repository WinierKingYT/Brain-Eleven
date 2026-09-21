# IG-07 Mimari Konsolidasyon: Envanter ve İlk Dilim Planı

**İncelenen revision:** `cb0255400a94c9d89b8859a016a8994c151f3329`
**Tarih:** 2026-09-10
**Kapsam:** Yalnızca okuma, envanter ve öneri. Bu doküman hazırlanırken `scripts/` veya `brain_eleven/` üretim dosyası değiştirilmedi. Phase 20 `FROZEN / LOCKED`, V2 `SHADOW` durumundadır.

## 1. Ölçüm yöntemi

- Envanter `scripts/*.py` altındaki **58 modülü** kapsar.
- `impl LOC`, boş satırlar ve ilk anlamlı karakteri `#` olan yorum satırları çıkarıldıktan sonra kalan satır sayısıdır. Docstring'ler bu sayıya dahildir; amaç fiziksel dosya boyutundan ziyade taşınacak mantığın yaklaşık hacmini göstermektir.
- `caller files / rg matches`, repository'deki izlenen `.py`, `.sh` ve `.md` dosyalarında `rg -n` ile bulunan açık modül/filename referanslarının benzersiz dosya ve satır eşleşmesi sayısıdır. Hedef modülün kendi dosyası dışarıda bırakıldı. Bu bir metinsel çağrı yüzeyi ölçüsüdür; dinamik çağrı grafiği veya çalışma zamanı frekansı değildir. Dokümantasyon ve migration-boundary testlerindeki referanslar da özellikle görünür bırakıldı.
- `last change`, `git log -1 --format='%cs|%h' -- scripts/<file>` çıktısındaki tarih ve kısa commit'tir.
- Bridge alanında `(_legacy)`, `brain_eleven._legacy.load_legacy_module` kullanımını; `(direct)`, `brain_eleven` içinden doğrudan `scripts.<module>` importunu gösterir. Direct import köprüleri `_legacy` cache sözleşmesinden farklı bir konsolidasyon borcudur.

Toplam hacim: **14.014 impl LOC / 17.345 fiziksel satır**. 25 modülün package tarafında bir köprü/consumer yüzeyi, 33 modülün ise halen yalnız script/operasyon yüzeyi vardır.

## 2. `scripts/` envanteri

| `scripts/` modülü | impl LOC | caller files / `rg` matches | son değişiklik | `brain_eleven/` köprüsü |
|---|---:|---:|---|---|
| `__init__.py` | 42 | 3 / 4 | 2026-09-09 / `09935e0` | yok |
| `anomaly_detector.py` | 250 | 3 / 3 | 2026-09-09 / `09935e0` | `brain_eleven/support/__init__.py` (`_legacy`) |
| `cache_manager.py` | 261 | 2 / 2 | 2026-09-09 / `09935e0` | `brain_eleven/support/__init__.py` (`_legacy`) |
| `capture_event.py` | 296 | 6 / 9 | 2026-09-09 / `09935e0` | `brain_eleven/runtime/worker.py` (`direct`) |
| `capture_queue.py` | 467 | 8 / 11 | 2026-09-10 / `1c6de6b` | `brain_eleven/runtime/worker.py` (`direct`) |
| `capture_safety.py` | 106 | 11 / 12 | 2026-08-31 / `a7ed63d` | `brain_eleven/extraction/semantic.py` (`_legacy`); `brain_eleven/runtime/{context,model,review,service,worker}.py` (`direct`) |
| `chat_interface.py` | 334 | 4 / 7 | 2026-09-09 / `09935e0` | yok |
| `check_context_engine_coverage.py` | 87 | 1 / 1 | 2026-09-05 / `f78ffc3` | yok |
| `context-compiler.py` | 468 | 11 / 14 | 2026-09-06 / `72eb441` | `brain_eleven/runtime/context.py` (`_legacy`, V1 bootstrap) |
| `context_engine_foundation_evidence.py` | 153 | 1 / 2 | 2026-09-05 / `8f55131` | yok |
| `dedupe-validated-memory.py` | 89 | 2 / 2 | 2026-09-06 / `ea0dd16` | yok |
| `demo-phase7-complete.py` | 207 | 0 / 0 | 2026-09-08 / `770294b` | yok |
| `dependency_audit.py` | 132 | 1 / 1 | 2026-09-02 / `857e004` | yok |
| `embedding-generator.py` | 218 | 7 / 7 | 2026-09-08 / `b8d8fa2` | yok |
| `entity_extractor.py` | 246 | 10 / 14 | 2026-09-09 / `09935e0` | `brain_eleven/extraction/__init__.py` (`direct`) |
| `evidence.py` | 341 | 8 / 9 | 2026-09-09 / `09935e0` | `brain_eleven/runtime/evidence.py`, `brain_eleven/runtime/worker.py` (`direct`) |
| `extraction.py` | 287 | 7 / 8 | 2026-09-09 / `09935e0` | `brain_eleven/extraction/semantic.py` (`_legacy`); `brain_eleven/runtime/worker.py` (`direct`) |
| `graduation_evidence.py` | 261 | 2 / 2 | 2026-09-02 / `0ed3d8d` | yok |
| `hybrid-search.py` | 192 | 8 / 8 | 2026-09-08 / `770294b` | `brain_eleven/search/__init__.py` (`_legacy`) |
| `install-cross-project-memory.py` | 311 | 2 / 9 | 2026-09-02 / `8f7dab8` | yok |
| `knowledge_graph.py` | 329 | 8 / 9 | 2026-09-09 / `09935e0` | `brain_eleven/graph/projection.py` (`direct`) |
| `logging_config.py` | 80 | 6 / 9 | 2026-08-30 / `56fe7a4` | `brain_eleven/support/__init__.py` (`_legacy`) |
| `memory-compiler.py` | 314 | 4 / 4 | 2026-09-02 / `cc35600` | yok |
| `memory-lifecycle.py` | 182 | 5 / 5 | 2026-09-06 / `8826117` | `brain_eleven/lifecycle/__init__.py` (`_legacy`) |
| `memory-retriever.py` | 197 | 6 / 6 | 2026-09-06 / `12b8c33` | `brain_eleven/search/__init__.py` (`_legacy`) |
| `memory-validator.py` | 720 | 9 / 11 | 2026-09-06 / `5d70931` | yok |
| `memory_backup.py` | 470 | 5 / 7 | 2026-09-07 / `7e6f55a` | yok |
| `memory_provenance.py` | 155 | 3 / 4 | 2026-09-09 / `09935e0` | yok |
| `memory_scope.py` | 193 | 9 / 16 | 2026-09-06 / `a8a171e` | `brain_eleven/memory/scope.py` (`_legacy`) |
| `memory_store.py` | 174 | 17 / 26 | 2026-09-09 / `09935e0` | `brain_eleven/memory/store.py` (`direct`) |
| `memory_store_lock.py` | 60 | 8 / 10 | 2026-08-31 / `88eacf2` | `brain_eleven/infrastructure/locking.py` (`_legacy`) |
| `memory_truth.py` | 410 | 5 / 6 | 2026-09-09 / `09935e0` | `brain_eleven/memory/truth.py` (`_legacy`); `brain_eleven/runtime/worker.py` (`direct`) |
| `migrate-legacy-memory.py` | 71 | 2 / 2 | 2026-09-06 / `bd90a55` | yok |
| `migrate-memory-scope.py` | 211 | 4 / 4 | 2026-09-06 / `bd90a55` | yok |
| `ml-ranker.py` | 201 | 5 / 5 | 2026-09-08 / `b8d8fa2` | `brain_eleven/search/__init__.py` (`_legacy`) |
| `phase15_evidence.py` | 157 | 1 / 1 | 2026-09-04 / `40c8233` | yok |
| `phase16_evidence.py` | 142 | 1 / 1 | 2026-09-04 / `40c8233` | yok |
| `phase17_evidence.py` | 213 | 1 / 1 | 2026-09-04 / `40c8233` | yok |
| `phase18_evidence.py` | 165 | 1 / 1 | 2026-09-04 / `40c8233` | yok |
| `phase19_evidence.py` | 189 | 1 / 1 | 2026-09-04 / `4f94005` | yok |
| `post_session_maintenance.py` | 120 | 3 / 7 | 2026-09-06 / `44c31b5` | yok |
| `project_registry.py` | 334 | 30 / 34 | 2026-09-09 / `09935e0` | `brain_eleven/projects/registry.py` (`direct`) |
| `prompt-counter.py` | 93 | 1 / 2 | 2026-09-01 / `399df66` | yok |
| `remember.py` | 180 | 10 / 13 | 2026-09-06 / `7156fc6` | yok |
| `remember_opt_in.py` | 16 | 2 / 2 | 2026-08-31 / `6b76fe6` | yok |
| `report_bandit_findings.py` | 50 | 1 / 1 | 2026-09-04 / `470d8df` | yok |
| `report_junit_failures.py` | 53 | 1 / 1 | 2026-09-04 / `bf5e906` | yok |
| `report_trivy_findings.py` | 56 | 1 / 1 | 2026-09-04 / `40c8233` | yok |
| `search-api.py` | 738 | 8 / 17 | 2026-09-09 / `ad6589f` | yok |
| `semantic-search.py` | 131 | 5 / 5 | 2026-09-08 / `b8d8fa2` | yok |
| `session_pipeline.py` | 217 | 3 / 4 | 2026-09-09 / `09935e0` | yok |
| `state.py` | 231 | 7 / 8 | 2026-09-06 / `72eb441` | yok |
| `state_boundary.py` | 294 | 5 / 5 | 2026-09-09 / `09935e0` | `brain_eleven/runtime/worker.py` (`direct`) |
| `state_resolver.py` | 186 | 7 / 11 | 2026-09-09 / `09935e0` | `brain_eleven/state/resolver.py` (`direct`) |
| `state_store.py` | 1072 | 23 / 28 | 2026-09-09 / `09935e0` | `brain_eleven/state/store.py` (`direct`) |
| `summarizer.py` | 204 | 7 / 8 | 2026-09-09 / `09935e0` | `brain_eleven/support/__init__.py` (`_legacy`) |
| `task_model.py` | 576 | 8 / 10 | 2026-09-09 / `09935e0` | yok |
| `task_state_context.py` | 82 | 26 / 26 | 2026-09-09 / `09935e0` | `brain_eleven/runtime/context.py` (`direct`) |

### Bridge-only modüller

Bu gruptaki `brain_eleven/` dosyası yeni mantık sahibi değildir; public package yüzeyi, re-export veya `_legacy` loader'dır. Gerçek implementasyon hâlâ `scripts/` dosyasındadır:

`anomaly_detector.py`, `cache_manager.py`, `entity_extractor.py`, `hybrid-search.py`, `knowledge_graph.py`, `logging_config.py`, `memory-lifecycle.py`, `memory-retriever.py`, `memory-scope.py`, `memory_store.py`, `memory_store_lock.py`, `memory_truth.py`, `ml-ranker.py`, `project_registry.py`, `state_resolver.py`, `state_store.py`, `summarizer.py`.

Bu, kopya implementasyon olmadığı için güvenli bir strangler başlangıcıdır; fakat package authority henüz `scripts/` dışına taşınmış değildir.

### Katmanlı / yarım kalmış taşıma yüzeyleri

Tam bir “eski dosya + aynı yeni dosya” kopyası tespit edilmedi. Ancak aşağıdaki modüller yeni package mantığının legacy implementation'a dayandığı katmanlı geçişlerdir ve IG-07'de ayrı ele alınmalıdır:

- **`context-compiler.py` → `brain_eleven/runtime/context.py`:** V2 task path'i package'lerde olsa da SessionStart V1 bootstrap, `_legacy` üzerinden bu scripti hâlâ yükler. V1/V2 authority ve fallback sınırı açıkça korunmalı.
- **`extraction.py` → `brain_eleven/extraction/semantic.py`:** semantic extractor yeni package'tedir; prefilter/legacy deterministic extractor hâlâ `scripts/extraction.py` olarak yüklenir. Bu iki katman aynı şey değildir, dolayısıyla ilk adım birleştirmek değil, bağımlılık sözleşmesini sabitlemektir.
- **`evidence.py` → `brain_eleven/runtime/evidence.py`:** transcript increment okuyucusu package'tedir, fakat `EvidenceStore` ve evidence modelleri scriptten direct import edilir. Veri modeli ile runtime adapter'ı tek authority altında toplamadan dosya silinmemeli.
- **Capture/truth/state stack:** `brain_eleven/runtime/worker.py` yeni orchestration implementation'ıdır; `capture_event.py`, `capture_queue.py`, `extraction.py`, `memory_truth.py` ve `state_boundary.py` onun legacy-backed dependenciesidir. Bunlar bir dosya taşıması değil, runtime ile domain implementation arasında katmanlı geçiştir.
- **Embedding/search:** `brain_eleven/retrieval/embedding_provider.py` explicit provider contract'ı sağlar; `embedding-generator.py`, `semantic-search.py`, `hybrid-search.py`, `memory-retriever.py` eski search path'ini korur. D0 reddi ve V2 SHADOW nedeniyle bu yüzey ilk dilime alınmamalıdır.

## 3. Risk kovaları

Risk, yalnız LOC veya caller sayısından değil; canonical veri etkisi, runtime kapsamı, güvenlik/lifecycle etkisi ve test sınırlarının netliğinden çıkarıldı. Aşağıdaki listeler 58 modülün tamamını bir kez içerir.

### Düşük risk

Saf/operasyonel yardımcılar, evidence/report üreticileri veya canonical truth yazmayan destek modülleri:

`__init__.py`, `anomaly_detector.py`, `cache_manager.py`, `check_context_engine_coverage.py`, `context_engine_foundation_evidence.py`, `dependency_audit.py`, `demo-phase7-complete.py`, `graduation_evidence.py`, `logging_config.py`, `phase15_evidence.py`, `phase16_evidence.py`, `phase17_evidence.py`, `phase18_evidence.py`, `phase19_evidence.py`, `prompt-counter.py`, `remember_opt_in.py`, `report_bandit_findings.py`, `report_junit_failures.py`, `report_trivy_findings.py`, `summarizer.py`.

Bu sınıfın “düşük” olması otomatik taşıma anlamına gelmez. `report_*`, phase evidence ve coverage dosyaları IG-07 hedefindeki production package implementation'ı değil, `scripts/` altında kalması gereken operasyon araçlarıdır.

### Orta risk

Canonical authority olmayan fakat birden çok davranış katmanına, CLI/migration yan etkisine veya kullanıcıya dönük akışa bağlı modüller:

`chat_interface.py`, `dedupe-validated-memory.py`, `entity_extractor.py`, `install-cross-project-memory.py`, `knowledge_graph.py`, `memory_provenance.py`, `migrate-legacy-memory.py`, `migrate-memory-scope.py`, `post_session_maintenance.py`, `remember.py`, `task_model.py`, `task_state_context.py`.

### Yüksek risk

Canonical persistence/state/project authority, capture/truth/lifecycle, scope/security veya production retrieval/context path'ini etkileyen modüller:

`capture_event.py`, `capture_queue.py`, `capture_safety.py`, `context-compiler.py`, `embedding-generator.py`, `evidence.py`, `extraction.py`, `hybrid-search.py`, `memory-compiler.py`, `memory-lifecycle.py`, `memory-retriever.py`, `memory-validator.py`, `memory_backup.py`, `memory_scope.py`, `memory_store.py`, `memory_store_lock.py`, `memory_truth.py`, `ml-ranker.py`, `project_registry.py`, `search-api.py`, `semantic-search.py`, `session_pipeline.py`, `state.py`, `state_boundary.py`, `state_resolver.py`, `state_store.py`.

Özellikle `MemoryStore`, `StateStore`, `ProjectRegistry` ve lock/scope/lifecycle bağımlılıkları ilk dilime alınmayacaktır. `capture_safety.py` ve `memory-validator.py` de doğrudan authority olmasalar bile güvenlik ve kabul kapısı oldukları için yüksek risklidir.

## 4. İlk dilim önerisi (yalnızca plan)

İlk dilim, davranış değişikliği veya canonical authority taşıması yapmadan `brain_eleven/support` içinde gerçek implementation authority oluşturmayı hedeflemelidir. Operational evidence/report scriptleri bilinçli olarak bu dilime alınmamalıdır.

### 4.1 `logging_config.py` → `brain_eleven/support/logging.py`

- **Değişecek:** JSON/colored formatter ve logger setup implementation'ı package içine taşınır; `brain_eleven/support/__init__.py` local implementation'ı expose eder. `scripts/logging_config.py` kısa süreli direct-execution/compatibility adapter olarak kalır.
- **Regresyon garantisi:** Yeni `tests/test_support_logging.py` formatter alanlarını, exception serialization'ı, handler tekrarını ve izole `log_dir` davranışını doğrulamalı. `tests/test_pre12_memory_state_caller_migration.py` import boundary'si ve tüm support caller testleri korunmalı.
- **Tahmini boyut:** 1 implementation commit + 1 caller/adapter commit; yaklaşık 80 LOC taşınır, adapter ve yeni testlerle yaklaşık 120–170 satır diff.
- **Risk notu:** Caller yüzeyi 6 dosya/9 eşleşme olmasına rağmen canonical state yazmaz. Mevcut doğrudan davranış testi eksik olduğu için test ekleme taşımanın ön koşuludur.

### 4.2 `cache_manager.py` → `brain_eleven/support/cache.py`

- **Değişecek:** LRU, disk fallback ve isteğe bağlı Redis facade implementation'ı package authority olur; `scripts/cache_manager.py` aynı public isimleri taşıyan thin adapter olarak kalır.
- **Regresyon garantisi:** `tests/test_performance.py` içindeki LRU eviction/TTL, disk persistence, get-or-compute, clear/delete ve concurrency testleri; ayrıca package/legacy object identity ve import boundary kontrolü.
- **Tahmini boyut:** 1 implementation + 1 caller/adapter commit; 261 LOC taşıma, yaklaşık 300–380 satır toplam diff.
- **Risk notu:** Yalnız 2 explicit caller dosyası vardır; Redis opsiyonel olduğundan migration default path'i L1/L3 ile sınırlı tutulmalıdır.

### 4.3 `summarizer.py` → `brain_eleven/support/summarizer.py`

- **Değişecek:** Tokenization, Jaccard dedup, digest ranking ve scope filtering package içine taşınır; script direct CLI adapter olarak korunur.
- **Regresyon garantisi:** `tests/test_phase10_summarizer_anomaly.py` digest/type ordering, dedup threshold, date extraction, empty/malformed memory ve markdown çıktısını; package/legacy identity testi public API eşitliğini doğrulamalı.
- **Tahmini boyut:** 1 implementation + 1 adapter/caller commit; 204 LOC taşıma, yaklaşık 240–320 satır diff.
- **Risk notu:** 7 caller dosyası/8 eşleşme vardır; retrieval ranking'i değiştirmeden yalnız import authority değiştirilmelidir.

### 4.4 `anomaly_detector.py` → `brain_eleven/support/anomaly.py`

- **Değişecek:** Structural/statistical anomaly detectors package implementation'ına taşınır; summarizer package surface'inden `tokenize`/`jaccard_similarity` kullanır. Script CLI/compatibility adapter kalır.
- **Regresyon garantisi:** `tests/test_phase10_summarizer_anomaly.py` yedi detector türünü, severity ordering'i, malformed input davranışını ve Markdown raporunu doğrulamalı. `summarizer.py` taşımasıyla birlikte package identity ve import boundary testi çalıştırılmalı.
- **Tahmini boyut:** 1 implementation + 1 adapter/caller commit; 250 LOC taşıma, yaklaşık 290–370 satır diff.
- **Risk notu:** 3 caller dosyası/3 eşleşme ve yalnız metadata/statistical kararlar vardır; canonical write path'e dokunulmaz.

### İlk dilim sırası

`logging_config.py` → `cache_manager.py` → `summarizer.py` → `anomaly_detector.py`.

Her modül için geçiş sonunda şu ortak kapı uygulanmalı:

1. package implementation ile legacy adapter object identity'si kanıtlanır;
2. `scripts/` içinde kalan dosya yalnız adapter/CLI olur, ikinci implementation oluşmaz;
3. eski import ve direct-execution yolları için parity testleri geçer;
4. full regression, critical flake8, compile/import sanity ve ilgili coverage çalışır;
5. bağımsız read-only review olmadan sonraki modüle geçilmez.

Bu dilim tamamlanmadan `MemoryStore`, `StateStore`, `ProjectRegistry`, capture/truth/lifecycle veya retrieval/context implementation'larına dokunulmamalıdır. Bu öneri IG-07 planıdır; bu commit'te hiçbir taşıma uygulanmamıştır.

## 5. Açık kararlar ve sınırlar

- Evidence/report, migration ve hook operation dosyalarının `scripts/` altında kalması IG-07 hedefiyle çelişmez; bunlar production implementation authority değil, thin operational entrypoint'lerdir.
- `brain_eleven/` içinde mevcut re-export dosyaları package yüzeyini standardize eder fakat implementation authority'yi henüz taşımaz. İlk dilim bu ayrımı support katmanında kanıtlamayı amaçlar.
- V1/V2 context, semantic extraction, embedding provider ve task-aware retrieval aynı anda konsolide edilmeyecektir. Bu alanlarda önce behavioral/evaluation gate'leri korunmalıdır.
- Bu envanter caller sayısını metinsel referans olarak verir; runtime execution frequency ve dynamic import edge'leri ayrıca bağımsız review sırasında doğrulanmalıdır.
