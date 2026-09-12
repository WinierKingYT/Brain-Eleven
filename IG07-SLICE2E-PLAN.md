# IG-07 Slice 2E — `task_model.py` Migration Plan

**Durum:** CLOSED / SHIPPED — implementation tamamlandı ve bağımsız
incelemeden `SHIP` aldı, bkz. `IG07-SLICE2E-PACKAGE-REPORT.md` ve
`IG07-SLICE2E-INDEPENDENT-REVIEW.md` (2026-09-12). Aşağıdaki plan metni,
bu doküman `09935e0` baseline'ından yeniden üretildiği için tarihsel bir
kayıt olarak korunuyor; "PLAN ONLY/REVIEW PENDING" ifadesi §0'da açıklanan
nedenle artık güncel değildir.
**Plan baseline:** `09935e0` (`IG07-INVENTORY.md` kaydındaki son legacy
uygulama revision'ı)
**Kapsam:** yalnız `scripts/task_model.py`
**Önerilen hedef:** `brain_eleven/runtime/task.py`
**Kapsam dışı:** `task_state_context.py` (Slice 2F), MemoryStore, StateStore,
ProjectRegistry implementasyonları, capture, retrieval, embedding/search,
context compiler/V1/V2 ve Phase 20.

Bu doküman hiçbir `.py` dosyasını değiştirmez ve package implementasyonu
oluşturma izni vermez.

## 0. Reality note: baseline ile mevcut HEAD ayrımı

İstenen envanter değerleri `09935e0` üzerinde tekrar doğrulandı:

- `scripts/task_model.py`: **668 fiziksel / 577 boş olmayan satır**;
- `git grep -n "task_model" 09935e0 -- '*.py'`: **8 dosyada 10 eşleşme**;
- o revision'da `brain_eleven/` tarafında task-model bridge'i yok.

Çalışma ağacının güncel HEAD'i `c7f8913` ise önceki oturumdan gelen
`brain_eleven/runtime/task.py` ve thin `scripts/task_model.py` adapter'ını
zaten içeriyor. Bu turda bu production değişikliklerini geri almıyor,
değiştirmiyor veya yeniden uygulamıyorum. Aşağıdaki plan, 09935e0'daki
legacy başlangıç durumunun bounded migration contract'ıdır; mevcut HEAD'deki
implementation bu planın bu turda onaylandığı anlamına gelmez.

## 1. Caller envanteri: 8 dosya / 10 eşleşme

Sayım, legacy başlangıç revision'ında şu komutla yapıldı:

```text
git grep -n "task_model" 09935e0 -- '*.py'
```

| Dosya | Satır | Eşleşme türü | Gerçek etkisi |
|---|---:|---|---|
| `scripts/task_state_context.py` | 14 | `from scripts.task_model import TaskAnalyzer, TaskEnvelope, TaskProjectResolutionError, TaskValidationError` | Production import |
| `scripts/task_state_context.py` | 18 | `from task_model import ...` fallback | Copied/deployed hook fallback |
| `authority/serialization.py` | 109 | function içi `TaskEnvelope` import'u | Authority JSON decode caller'ı |
| `evals/task_state_eval.py` | 19 | `from scripts.task_model import TaskAnalyzer` | Offline evaluation caller'ı |
| `tests/test_task_model.py` | 14 | bare task-model contract import'u | Behavioral test caller'ı |
| `tests/test_pre12_project_caller_migration.py` | 13 | `task_model.ProjectRegistry` | Compatibility test caller'ı |
| `tests/test_pre12_project_caller_migration.py` | 14 | `task_model.ProjectRegistryError` | Compatibility test caller'ı |
| `conftest.py` | 75 | test alias listesi | Test bootstrap, runtime caller değil |
| `scripts/check_context_engine_coverage.py` | 21 | coverage path string'i | Static inventory, runtime caller değil |
| `tests/test_context_engine_coverage.py` | 23 | coverage path string'i | Static inventory, runtime caller değil |

Sonuç:

- Inventory lexical sayımı: **8 dosya / 10 eşleşme**, doğrulandı.
- Gerçek production import dosyaları: **3** (`task_state_context.py`,
  `authority/serialization.py`, `evals/task_state_eval.py`).
- Gerçek behavioral test caller dosyaları: **2** (`test_task_model.py`,
  `test_pre12_project_caller_migration.py`).
- Bootstrap/coverage metadata: **3**, caller sayısına dahil edilmemeli fakat
  migration sonrası static gate olarak korunmalı.

`task_state_context.py`'nin kendisi daha geniş 26+ caller blast radius'una
sahiptir; bu tablo yalnız onun `task_model.py` dependency edge'ini gösterir.
`brain_eleven/runtime/context.py`, router, authority shadow ve eval provider
dosyaları task modelini doğrudan değil `task_state_context.py` üzerinden
kullanır; Slice 2F envanterine aittir.

## 2. Legacy implementasyon haritası

Satır referansları `09935e0:scripts/task_model.py`'ye aittir. `@dataclass`
dekoratörleri bir önceki satırda bulunduğundan aralıklar dekoratör gövdesini
de kapsar.

### 2.1 Modül sabitleri ve dış bağımlılık

- **1-5:** CLI modül docstring'i; task envelope'ın invocation contract'ı
  olduğunu ve memory selection yapmadığını belirtir.
- **8-18:** yalnız stdlib (`json`, `re`, `secrets`, `time`, `argparse`,
  dataclass, datetime, pathlib, typing) import'ları.
- **20:** `brain_eleven.projects.registry` üzerinden
  `ProjectRegistry`/`ProjectRegistryError` import'u. Registry yalnız proje
  kimliği çözümleme için okunur.
- **23-59:** schema/namespace ve vocabulary sabitleri:
  `TASK_SCHEMA_VERSION`, `TASK_ID_PREFIX`, lifecycle/status kümeleri,
  `INTENTS`, `OPERATIONS`, `RISK_LEVELS`, `REQUESTED_OUTPUTS`,
  `EVIDENCE_SOURCES`, `MAX_REQUEST_CHARS` ve Crockford alphabet.

Legacy kaynak üzerinde `MemoryStore`, `StateStore`, `open`, `write_text`,
`transact`, `replace`, `register` veya canonical memory/state mutation çağrısı
bulunmadı. Task modelinin persistence authority'si yoktur; yine de bu
özellik Gate 3'te AST ve runtime evidence ile yeniden kanıtlanmalıdır.

### 2.2 Hatalar, kurallar ve deterministic analyzer

- **62-68:** `TaskValidationError` ve `TaskProjectResolutionError`.
- **70-73:** immutable `_Rule` dataclass.
- **76-147:** intent/domain/constraint/risk rule tabloları ve phrase sözlüğü.
- **150-167:** `utc_now`, Crockford encoder ve `new_task_id`; ID üretimi
  process-local/random'dır, canonical write değildir.
- **170-192:** `resolve_project(vault_path, project_root)`;
  `ProjectRegistry.resolve` çağırır, registry hatasını
  `TaskProjectResolutionError` olarak görünür kılar, unknown project'i
  `unresolved` döndürür, kayıt açmaz.
- **195-268:** request normalization, word-boundary phrase matching, rule
  collection/confidence, entity extraction, risk level ve context-needs
  çıkarımı.
- **271-341:** `TaskAnalyzer`; request'i normalize eder, project resolution
  alır, intent/domain/constraint/risk/context ihtiyaçlarını deterministic
  olarak üretir ve son olarak `TaskEnvelope.from_dict(envelope.to_dict())`
  ile schema doğrulaması yapar.

### 2.3 Veri modelleri ve validation

- **344-387:** `_require_string`, `_require_confidence`,
  `_require_string_tuple`, `_mapping`, `_exact_keys`.
- **390-412:** `Evidence` frozen dataclass; value/source/confidence provenance.
- **415-454:** `ProjectResolution`; resolved/unresolved/archived statüleri,
  project-id zorunlulukları ve confidence.
- **457-618:** `TaskEnvelope` frozen dataclass; schema v1, `tsk_` namespace,
  lifecycle, nested evidence, constraints, domains, risk, context needs,
  ambiguity, confidence ve parent/continuation linkleri.
- **621-628:** `validate_task` ve deterministic `render_task_json`.
- **631-643:** persistence'siz human summary.
- **646-668:** `analyze` subcommand'ı ve direct CLI `main`.

### 2.4 Phase 16 ilişkisi

`PROJECT-STATUS.md:158-172`, Phase 16'nın üç authority'sini
`MemoryStore`, `ProjectRegistry`, `StateStore` olarak ayırır ve task-model
CLI'sını deterministic task envelope inspection aracı olarak tanımlar.
`task_model.py` bu modelde yalnız request/task contract üretir:

- `ProjectRegistry` → mevcut project identity/status read-only çözümlemesi;
- `TaskEnvelope` → invocation input contract;
- `StateStore`/`MemoryStore` → task modelinin dışında, ayrı authorities;
- `evals/task_state_eval.py` → offline public/holdout ölçümü.

Taşıma bu sınırları birleştirmemeli, task analyzer'ı state veya memory writer'a
dönüştürmemeli, Phase 16 evaluator'ını tuning yüzeyine çevirmemelidir.

## 3. Önerilen package ve adapter sözleşmesi

### 3.1 Hedef

Canonical implementation: `brain_eleven/runtime/task.py`.
`brain_eleven/runtime/__init__.py` içinden eager re-export zorunlu değildir;
canonical import yüzeyi açıkça `brain_eleven.runtime.task` olarak kalmalıdır.

### 3.2 Thin adapter

`scripts/task_model.py` yalnız şu sorumlulukları taşıyabilir:

1. repo root'u güvenli biçimde `sys.path`e eklemek;
2. `brain_eleven.runtime.task` modülünü bir kez yükleyip cache'lemek;
3. canonical sabit, class, exception ve function isimlerini re-export etmek;
4. historical `ProjectRegistry`/`ProjectRegistryError` erişimini korumak;
5. `sys.modules['scripts.task_model']` ve bare `task_model` fallback alias'ını
   korumak;
6. `python scripts/task_model.py analyze ...` çağrısını canonical `main()`e
   delege etmek.

Adapter'da ikinci dataclass/class, rule tablosu, analyzer, schema validator,
JSON/file write, registry mutation veya alternative CLI implementasyonu
olamaz. Private helper'lar compatibility için alias yapılabilir; yeniden
tanımlanamaz.

### 3.3 `task_state_context.py` sınırı

`task_state_context.py:14` normal package import'u, `:18` copied-hook fallback'i,
`:45` analyzer construction'ı, `:49-67` envelope merge/round-trip'i ve
`:70-86` compose/error yüzeyini kullanır. Migration yalnız adapter identity'si
korunarak yapılırsa bu dosyanın davranışsal etkisi sıfır olabilir.

Bu iddia ancak şu beş koşulla geçerlidir:

- import isimleri ve bare fallback korunur;
- `TaskAnalyzer`, `TaskEnvelope` ve iki exception aynı object identity'de kalır;
- JSON key seti, key sırası, schema ve default değerler değişmez;
- registry resolution hata/unknown/archived semantiği değişmez;
- deterministic rule tabloları, confidence ve context-needs çıktıları değişmez.

Bir koşul sağlanamazsa geçici uyumluluk kodu yazılmaz; migration durur ve
`RETHINK/defer` raporlanır. `task_state_context.py` bu Slice 2E'de
değiştirilemez; kendi migration'ı Slice 2F'dir.

## 4. Migration invariant'ları

### Contract ve behavior

- `TASK_SCHEMA_VERSION=1`, `tsk_` ID namespace ve lifecycle/status kümeleri
  birebir kalır.
- `TaskEnvelope.to_dict()` key seti ve deterministic field order değişmez.
- Valid/invalid JSON, unknown key, missing key, confidence, source,
  lifecycle, project status ve namespace hataları aynı exception sınıfını ve
  görünür mesaj semantiğini korur.
- Turkish/English intent/domain/constraint/risk/entity/context-needs çıktıları
  exact parity gösterir.
- `new_task_id` uzunluğu/prefix'i ve `utc_now` formatı korunur.
- `resolve_project` read-only kalır; unknown, archived, relocated ve corrupt
  registry davranışı değişmez.
- Analyzer hiçbir MemoryStore/StateStore/ProjectRegistry write yolu açmaz.
- `main --json` ve human summary yalnız task contract üretir; canonical state,
  memory veya eval corpus yazmaz.

### Caller parity

Değişmeden çalışan production callers:

- `scripts/task_state_context.py` normal/fallback import ve compose;
- `authority/serialization.py:task_state_from_dict` strict task decode;
- `evals/task_state_eval.py` task case execution.

Değişmeden çalışan test/tool surfaces:

- `tests/test_task_model.py`;
- `tests/test_pre12_project_caller_migration.py`;
- `conftest.py` bare alias bootstrap;
- iki context-coverage path listesi.

## 5. Test planı

### Existing tests — source değişmeden

Minimum suite:

```text
tests/test_task_model.py
tests/test_task_state_context.py
tests/test_context_router.py
tests/test_context_engine_operational_surfaces.py
tests/test_context_compiler_v2.py
tests/test_context_compiler_v2_hardening.py
tests/test_authority_resolver.py
tests/test_task_state_eval.py
tests/test_pre12_project_caller_migration.py
tests/test_pre12_memory_state_caller_migration.py
```

### New bounded tests

- package/adapter/bare `TaskAnalyzer`, `TaskEnvelope`, `Evidence`,
  `ProjectResolution`, errors, constants and public functions identity;
- `TaskEnvelope.from_dict.__func__` classmethod identity;
- adapter-only AST: zero class/dataclass/validator/rule implementation;
- adapter'da zero `open`, JSON persistence, MemoryStore/StateStore access;
- old/new CLI JSON shape parity (dynamic task id/timestamp normalized only for
  comparison);
- known/unknown/archived/relocated/corrupt registry parity;
- Turkish/English deterministic analyzer fixtures;
- `task_state_context.py` byte diff empty;
- authority `task_state_from_dict` parity;
- before/after evaluator equality for smoke, public ve holdout.

Holdout labels, fixtures, thresholds and evaluator source'u test tuning için
kullanılamaz veya değiştirilemez.

## 6. Tahmini diff büyüklüğü

Legacy başlangıç implementation'ı **668 fiziksel / 577 boş olmayan satır**tır.
Beklenti:

- `brain_eleven/runtime/task.py`: **660-700 satır** taşınan implementation;
- `scripts/task_model.py`: **70-120 satır** loader/re-export adapter;
- yeni identity/parity tests: **120-220 satır**;
- package report/contract: **100-180 satır** dokümantasyon;
- toplam bounded code/test diff: yaklaşık **850-1.040 satır**.

Bu tahmin taşınan kod ağırlıklıdır; yeni semantic feature, rule tuning veya
task-state refactor içermez.

## 7. Beş kapılı exit gate

### Gate 1 — Identity

Package, `scripts.task_model` ve bare `task_model` yüzeyleri aynı object'leri
verir: tüm public constants, `TaskAnalyzer`, `TaskEnvelope`, `Evidence`,
`ProjectResolution`, iki error, `ProjectRegistry` compatibility names,
`new_task_id`, `resolve_project`, `validate_task`, `render_task_json` ve
`main`. Classmethod underlying function identity de kontrol edilir.

### Gate 2 — Adapter-only

AST/grep kanıtı: adapter'da class/dataclass, analyzer/rule/validation helper,
JSON/file write, registry mutation veya duplicate CLI implementation yoktur.
Canonical source package-owned import yüzeylerini kullanır.

### Gate 3 — Parity + safety

Existing tests değişmeden geçer; task/state/authority/eval caller çıktıları
before/after exact karşılaştırılır. `task_state_context.py` byte diff boş,
registry read-only, persistence write sayısı sıfır, holdout corpus immutable
olmalıdır. Fark çıkarsa fixture/label değiştirilmez; migration düzeltilir veya
`RETHINK/defer` verilir.

### Gate 4 — Full verification

```text
python -m pytest tests -q
python -m flake8 brain_eleven/runtime/task.py scripts/task_model.py tests/test_task_model_package_migration.py --select=E9,F63,F7,F82
python -m compileall -q brain_eleven/runtime/task.py scripts/task_model.py
git diff --check
```

Exact HEAD, test sonuçları, before/after evaluator JSON'ları ve warning'ler
package report'a bağlanır.

### Gate 5 — Independent review

Ayrı read-only reviewer; baseline revision, caller listesi, byte/parity,
adapter AST, task-state context değişmezliği, authority serialization,
holdout immutability ve full verification kanıtını inceler. Karar yalnız
`SHIP`, `FIX-FIRST` veya `RETHINK` olabilir. Self-review `SHIP` değildir.

## 8. Package report şablonu

Uygulama yetkisi verildiğinde rapor aşağıdaki alanları doldurmalıdır:

```text
PACKAGE: IG-07 / Slice 2E
REVISION: <exact implementation/evidence SHA>
OBJECTIVE: <bounded task-model inversion objective>
FILES CHANGED: <canonical, adapter, tests, evidence>
ROOT CAUSES ADDRESSED: <implementation authority / compatibility causes>
TESTS ADDED: <identity, AST, parity, safety>
TESTS EXECUTED: <focused, full, lint, compile, diff>
QUALITY METRICS BEFORE: <baseline suite/evaluator outputs>
QUALITY METRICS AFTER: <after suite/evaluator outputs>
SAFETY METRICS: <write paths, read-only registry, leakage, holdout integrity>
KNOWN LIMITATIONS: <remaining task_state_context / warnings>
OPEN FAILURES: <P0/P1/P2 or none>
INDEPENDENT REVIEW: <SHIP / FIX-FIRST / RETHINK + reviewer evidence>
SCORE BEFORE: <score or not rescored>
SCORE AFTER: <score or not rescored>
VERDICT: SHIP / FIX-FIRST / RETHINK / REVIEW PENDING
```

## 9. Unexpected-risk stop condition

Plan sırasında şu bulgulardan biri ortaya çıkarsa implementation kapsamı
genişletilmeyecek ve ayrı `RETHINK/defer` bulgusu yazılacaktır:

- task modelinin gizli MemoryStore/StateStore/registry write yolu;
- task_state_context.py ile adapter identity korunarak ayrıştırılamayan davranış;
- authority serialization'ın task model private implementation detayına
  bağımlılığı;
- holdout fixture/label/threshold değişikliği gerektiren bir parity farkı;
- canonical module ile legacy adapter arasında iki farklı schema/error
  authority oluşması.

Bu planın incelemesi tamamlanmadan hiçbir production `.py` dosyası değişmez.

**Plan status: CLOSED — implementation (E1+E2) tamamlandı, bağımsız inceleme
`SHIP` verdiği verdi. Bkz. `IG07-SLICE2E-PACKAGE-REPORT.md`,
`IG07-SLICE2E-INDEPENDENT-REVIEW.md`.**
