# IG-07 Slice 2E — `task_model.py` Migration Plan

**Durum:** PLAN ONLY — bu doküman implementasyon izni vermez.
**Plan temeli:** `971726bf7434ef47386007e95b5b13aa20af84a6` (`origin/master`)
**Kapsam:** yalnız `scripts/task_model.py` için package yönünün çevrilmesi.
**Hedef:** `brain_eleven/runtime/task.py`
**Hariç:** `scripts/task_state_context.py`, `MemoryStore`, `StateStore`,
`ProjectRegistry` implementasyonu, capture/retrieval ve Phase 20.

## 1. Karar özeti

`task_model.py` halen script içinde gerçek implementasyonu taşıyor ve mevcut
package katmanında bir köprü bulunmuyor. `task_state_context.py` bu modülü
doğrudan kullanan, 26+ caller'lı ayrı ve daha geniş bir migration alanıdır.

Öneri, `task_model.py`'yi `brain_eleven/runtime/task.py` içine **salt yön
çevirme** olarak taşımaktır. Bu, `task_state_context.py`'yi şimdi taşımak veya
değiştirmek anlamına gelmez. `scripts/task_model.py` aynı public isimleri
package modülünden yükleyen thin adapter olarak kaldığı sürece:

- `task_state_context.py`'nin import satırları değişmeden kalabilir;
- `TaskAnalyzer`, `TaskEnvelope` ve hata sınıfları aynı object identity'yi
  korur;
- `authority/serialization.py` ve `evals/task_state_eval.py` mevcut import
  yollarıyla çalışmaya devam eder;
- task/state context davranışı için yeni bir semantic değişiklik yapılmaz.

Bu nedenle modülü sonsuza kadar ertelemek yerine, **ayrı bounded contract,
exact baseline ve bağımsız review sonrasında** Slice 2E olarak ele almak daha
güvenlidir. Ancak bu hâlâ HIGH riskli bir pakettir: 668 fiziksel satır,
schema doğrulama, proje çözümleme, authority serialization ve holdout eval
aynı public yüzeye bağlıdır. Taşıma sırasında refactor, yeni kural, keyword
tuning veya `task_state_context.py` değişikliği yapılmayacaktır.

## 2. Güncel envanter ve caller kanıtı

Caller sayısı, hedef script dışındaki Python dosyalarında gerçek import veya
runtime referansına göre sayıldı. Docstring'ler, yorumlar ve yalnızca statik
migration listeleri sayılmadı. `conftest.py`'nin bare-module alias'ı test
bootstrap kanıtıdır; production caller değildir.

### 2.1 `scripts/task_model.py`

| Ölçüm | Güncel durum |
|---|---|
| Fiziksel satır | 668 |
| Boş olmayan satır | 577 |
| Son değişiklik | 2026-09-10 (`git log -1`) |
| Mevcut package bridge | Yok; gerçek implementasyon scriptte |
| Önerilen canonical modül | `brain_eleven/runtime/task.py` |
| Doğrudan production caller | 3 dosya |
| Doğrudan test caller | 2 dosya |

### 2.2 Gerçek production caller'lar

1. **`scripts/task_state_context.py:14-18`**
   `TaskAnalyzer`, `TaskEnvelope`, `TaskProjectResolutionError` ve
   `TaskValidationError` için önce `scripts.task_model`, yalnız deployed
   copied-hook fallback durumunda bare `task_model` import eder. Bu dosya
   Slice 2E'de değiştirilmeyecek.

2. **`authority/serialization.py:106-115`**
   `task_state_from_dict()` içinde `TaskEnvelope`'ı process sınırından gelen
   JSON task bölümünü doğrulamak için dinamik olarak import eder ve
   `TaskEnvelope.from_dict()` çağırır. Bu kullanım authority store'a yazmaz;
   strict schema/content-free decode sınırıdır.

3. **`evals/task_state_eval.py:19,135-158`**
   `TaskAnalyzer` ile task case'lerini offline ve deterministic olarak
   değerlendirir. Bu eval harness production path değildir, fakat public ve
   holdout sonuçlarının migration öncesi/sonrası aynı kalması gerekir.

### 2.3 Gerçek test caller'lar

1. **`tests/test_task_model.py:14-21`** — task schema round-trip, validation,
   task id, project resolution ve deterministic analyzer davranışı.
2. **`tests/test_pre12_project_caller_migration.py:13-14`** — `ProjectRegistry`
   ve `ProjectRegistryError` isimlerinin historical `task_model` yüzeyinden
   erişilebilir olmasını kontrol eden compatibility caller.

Dolaylı fakat migration kanıtı olarak mutlaka çalıştırılacak test yüzeyleri:

- `tests/test_task_state_context.py`
- `tests/test_context_router.py`
- `tests/test_context_engine_operational_surfaces.py`
- `tests/test_context_compiler_v2.py`
- `tests/test_context_compiler_v2_hardening.py`
- `tests/test_authority_resolver.py`
- `tests/test_task_state_eval.py`
- `tests/test_pre12_memory_state_caller_migration.py`
- `tests/test_pre12_project_caller_migration.py`

`brain_eleven/runtime/context.py`, `authority/shadow.py`, router benchmark ve
diğer eval provider'lar `task_model.py`yi doğrudan değil,
`task_state_context.py` üzerinden kullanır. Bunlar 26+ caller'lı ayrı
`task_state_context.py` migration'ının blast radius'udur; bu planda caller
listesine doğrudan task-model caller'ı olarak eklenmez.

## 3. Gerçek implementasyon yapısı

`task_model.py` yalnızca deterministic task-envelope üretir ve doğrular; kendi
başına MemoryStore/StateStore/capture/retrieval yazımı yapmaz.

### 3.1 Sabitler ve authority import'ı

- `ProjectRegistry`, `ProjectRegistryError`: **20. satır**; package registry
  yüzeyinden gelir ve historical `task_model.ProjectRegistry` erişimi nedeniyle
  adapter tarafından da re-export edilmelidir.
- Schema/namespace sabitleri: **23-59** — `TASK_SCHEMA_VERSION=1`, `tsk_`
  prefix, lifecycle/status kümeleri, intent/operation/risk/output/evidence
  kümeleri, `MAX_REQUEST_CHARS` ve Crockford alphabet.

### 3.2 Hata, kural ve analiz yüzeyi

- `TaskValidationError`: **62-64**
- `TaskProjectResolutionError`: **66-68**
- `_Rule`: **70-73**
- zaman/id ve project read-only çözümleme: `utc_now` **150-152**,
  `_encode_crockford` **155-160**, `new_task_id` **163-167**,
  `resolve_project` **170-192**
- deterministic text/rule helpers: **195-268** — normalize, word-boundary
  phrase match, rule collection/confidence, entity extraction, risk level ve
  context-needs çıkarımı.

### 3.3 Public analyzer ve envelope modelleri

- `TaskAnalyzer`: **271-341**; registry üzerinden yalnız okur, request'i
  intent/domain/constraint/risk/context-need alanlarına ayırır ve
  `TaskEnvelope.from_dict(envelope.to_dict())` ile son schema doğrulaması yapar.
- validation helpers `_require_string`–`_exact_keys`: **344-387**.
- `Evidence`: **390-412**, value/source/confidence provenance alanıdır.
- `ProjectResolution`: **415-454**; resolved/unresolved/archived ayrımını ve
  project id zorunluluklarını doğrular.
- `TaskEnvelope`: **457-618**; immutable dataclass, schema v1 round-trip,
  task id namespace, lifecycle, nested evidence, confidence ve optional parent/
  continuation id doğrulamasını taşır.
- `validate_task`: **621-623**, `render_task_json`: **626-628**,
  human summary: **631-643**, direct CLI `main`: **646-668**.

Taşıma hedefinde bu sınırların tamamı tek canonical implementasyon olarak
`brain_eleven/runtime/task.py` içinde kalır. Adapter yalnız loader, re-export,
legacy alias ve direct CLI delegation içerir.

## 4. `task_state_context.py` bağımlılığı ve öneri

`task_state_context.py`'nin import ve kullanım haritası:

- **14. satır:** `from scripts.task_model import ...`
- **18. satır:** yalnız `scripts` paketi yoksa bare `task_model` fallback'i
- **45. satır:** `TaskAnalyzer` constructor'ı
- **49-67:** `TaskEnvelope` üzerinde state'ten inherited constraint ve
  `context_needs` birleştirmesi; sonucu `TaskEnvelope.from_dict()` ile yeniden
  doğrular
- **70-72:** task analizi + `StateResolver` çağrısı ile
  `TaskStateContext` oluşturur
- **84-86:** task model hata sınıflarını CLI hata cevabına dönüştürür.

Bu bağımlılıkta davranışsal olarak sıfır etki mümkündür, çünkü adapter:

1. `scripts.task_model` adını korur;
2. bare `task_model` alias'ını korur;
3. bütün public class/function/constant nesnelerini canonical modülden tekrar
   export eder;
4. exception class identity'sini değiştirmez;
5. `TaskEnvelope` JSON şekline, field sırasına, default değerlerine veya
   `TaskAnalyzer` rule tablolarına dokunmaz.

Bu şartlardan biri sağlanamıyorsa migration durur; `task_state_context.py`ye
geçici uyumluluk kodu eklenmez. `task_state_context.py`nin kendi migration'ı
ayrı bir plan ve ayrı blast-radius review olarak kalır.

## 5. Authority serialization ve evaluation güvenlik sınırı

### 5.1 `authority/serialization.py`

`task_state_from_dict()` yalnızca `TaskEnvelope.from_dict()` çağırır; task
modeli authority truth yazmaz, state snapshot'ını da `CurrentProjectState`
olarak decode eder. Package migration sonrasında:

- `TaskEnvelope` class identity'si aynı kalmalı;
- schema version `1`, exact keys, `tsk_` namespace, source/confidence ve
  unresolved/resolved project kuralları değişmemeli;
- content-free authority serialization kuralı etkilenmemeli;
- `authority/__main__.py` üzerinden decode edilen JSON çıktısı ve hata türleri
  byte/parity testinde aynı kalmalı;
- authority resolver'ın task/state input validation'ı yeni bir import yan
  etkisiyle bypass edilmemeli.

Bu migration `authority/serialization.py`yi veya authority modellerini
değiştirmez. Gerekli adapter import değişikliği package yüzeyinden değil,
legacy `scripts.task_model` compatibility yüzeyinden karşılanır.

### 5.2 `evals/task_state_eval.py` ve holdout immutability

`evals/task_state_eval.py` içinde `_TASK_CASES` ve `_STATE_CASES` sabit tuple
olarak tanımlıdır; `SUITES` smoke/public/holdout/all ayrımını yapar. Task
model migration'ı:

- eval dosyasına,
- case label'larına,
- holdout request/status/expected değerlerine,
- provider/schema version'a,
- evaluation ağırlıklarına veya threshold'larına

dokunmayacaktır.

Migration öncesi ve sonrası aynı exact revision ile şu raporlar alınacaktır:

```text
python -m evals.task_state_eval --suite smoke --report before-smoke.json
python -m evals.task_state_eval --suite public --report before-public.json
python -m evals.task_state_eval --suite holdout --report before-holdout.json
```

Sonuçlar `task_cases`, `state_cases`, `metrics`, `invariants`, provider ve
schema alanlarında karşılaştırılacak; geçici dizin adları rapora girmediği için
deterministic public/holdout eşitliği aranacaktır. Holdout yalnız doğrulama
olarak okunur; başarısızlık varsa task rules veya labels değiştirilerek
gizlenmez. `git diff -- evals/task_state_eval.py evals/` boş olmalıdır.

## 6. Önerilen migration sınırı

### Step E1 — contract ve baseline (önkoşul)

- `brain_eleven/runtime/task.py` public export listesi ve legacy isim matrisi
  yazılı contract'a alınır.
- `scripts/task_model.py` için adapter-only AST kriteri belirlenir.
- Task model, task-state context, authority serialization ve eval public/
  holdout snapshot'ları migration öncesi kaydedilir.
- Bu adımda production davranışı değiştirilmez.

### Step E2 — canonical inversion

- `scripts/task_model.py` implementasyonu byte/parity korunarak
  `brain_eleven/runtime/task.py` içine alınır.
- Imports package-owned `brain_eleven.projects.registry` yüzeyinde kalır.
- `scripts/task_model.py` `_load_canonical`/`importlib` adapter'ına indirilir;
  `TaskAnalyzer`, `TaskEnvelope`, tüm sabitler, validation helpers'ın public
  olması gerekenleri, `ProjectRegistry`/`ProjectRegistryError`,
  `validate_task`, `render_task_json`, `main` re-export edilir.
- `sys.modules['task_model']` ve `scripts.task_model` compatibility alias'ları
  korunur; direct `python scripts/task_model.py analyze ...` CLI package
  `main()` fonksiyonuna delegasyon yapar.
- `task_state_context.py`, `authority/serialization.py` ve eval harness bu
  adımda değiştirilmez.

### Step E3 — evidence and closure

Focused tests, exact before/after eval comparison, full regression, critical
lint/compile checks ve bağımsız read-only review tamamlanır. Reviewer SHIP
vermeden Slice 2E kapanmaz; task_state_context migration'ı açılmaz.

## 7. Beş kapılı kanıt planı

### Gate 1 — identity

Aşağıdaki isimler için package, `scripts.task_model` ve bare `task_model`
aynı object olmalıdır:

- `TaskAnalyzer`, `TaskEnvelope`, `Evidence`, `ProjectResolution`;
- `TaskValidationError`, `TaskProjectResolutionError`;
- `TASK_SCHEMA_VERSION`, `TASK_ID_PREFIX`, `TASK_LIFECYCLES`,
  `PROJECT_RESOLUTION_STATUSES`, `INTENTS`, `OPERATIONS`, `RISK_LEVELS`,
  `REQUESTED_OUTPUTS`, `EVIDENCE_SOURCES`;
- `new_task_id`, `resolve_project`, `validate_task`, `render_task_json`;
- compatibility için `ProjectRegistry` ve `ProjectRegistryError`.

`TaskEnvelope.from_dict` gibi classmethod referansları da canonical class
üzerinde çalıştığı ayrıca gösterilecektir.

### Gate 2 — adapter-only AST

`scripts/task_model.py` içinde ikinci class/dataclass, analyzer/rule helper,
schema validation, JSON persistence veya registry write kodu kalmayacak. İzin
verilenler: root path kurulumu, canonical loader/cache, re-export tabloları,
legacy bare alias ve `main()` delegation. `open`, `json.dump`, `MemoryStore`,
`StateStore` ve direct registry mutation AST/grep kontrollerinde bulunmayacak.

### Gate 3 — parity and safety

- `tests/test_task_model.py` değişmeden geçer.
- task envelope valid/invalid round-trip, unknown key, invalid source,
  confidence, lifecycle, namespace ve project status parity'si korunur.
- Turkish/English intent, ambiguity, entity, risk ve context-needs çıktıları
  exact karşılaştırılır.
- known/unknown/archived/relocated/corrupt registry çözümlemesi aynı olur ve
  analyzer registry'ye yeni kayıt yazmaz.
- `task_state_context.py` byte diff'i boştur; compose sonucu ve exception
  identity'si E2E karşılaştırılır.
- `authority/serialization.py` task-state decode ve authority CLI parity'si
  korunur.
- `evals/task_state_eval.py` public ve holdout raporlarında case id, metrics,
  invariant ve failure listeleri değişmez.
- direct CLI (`analyze --json` ve human summary) package/legacy yollarında
  aynı çıktıyı verir; no-network/no-persistence koşulu korunur.

### Gate 4 — full verification

Minimum odaklı suite:

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

Ardından:

```text
python -m pytest tests -q
python -m flake8 brain_eleven/runtime/task.py scripts/task_model.py \
  tests/test_task_model_package_migration.py --select=E9,F63,F7,F82
python -m compileall -q brain_eleven/runtime/task.py scripts/task_model.py
git diff --check
```

Exact revision, test sonucu ve holdout raporları package report'a yazılır.

### Gate 5 — independent review

Reviewer implementasyon reasoning'ini devralmadan şunları kontrol eder:

- package/adapter/bare identity ve adapter-only AST;
- `task_state_context.py`nin gerçekten değişmediği;
- `authority/serialization.py` ve eval dosyalarının contract dışı
  değişmediği;
- task model byte/parity, read-only registry davranışı ve CLI;
- holdout label/fixture/tuning gizleme girişimi olup olmadığı;
- full regression ve exact evidence revision'ı.

Karar yalnız `SHIP`, `FIX-FIRST` veya `RETHINK` olabilir. Bu plan ve olası
uygulama kendi kendine SHIP vermez.

## 8. Risk kararı

**Risk:** HIGH remains.

Gerekçe: düşük direct writer riski olsa da task model, task-state context'in
en yoğun bağımlılığıdır; schema/error identity ve deterministic analyzer
çıktıları authority serialization, router/compiler zinciri ve holdout eval
sonuçlarına yayılır. Ayrıca historical `task_model.ProjectRegistry` export'u
adapter compatibility'sini zorunlu kılar.

Risk azaltma stratejisi:

- `task_state_context.py` değişmeden kalır;
- canonical implementation byte/parity ile taşınır;
- package/legacy/bare identity zorunlu tutulur;
- eval corpus ve holdout immutable kalır;
- full suite ve bağımsız reviewer olmadan sonraki migration açılmaz.

Bu plan, task model'in davranışını iyileştirme veya task understanding tuning'i
önermemektedir. Eğer E1 baseline/parity kanıtı üretilemezse sonuç **RETHINK /
defer** olur ve implementasyon başlamaz.

## 9. Tahmini diff ve sıralama

Beklenen bounded değişiklik:

- `brain_eleven/runtime/task.py`: yaklaşık **668 fiziksel / 577 boş olmayan
  satır** implementation taşınması;
- `scripts/task_model.py`: yaklaşık **80–120 satır** thin adapter;
- package export/identity ve adapter parity testleri: yaklaşık **180–260
  satır**;
- toplam diff: yaklaşık **930–1.050 satır** (taşınan kod ağırlıklı; yeni
  semantic davranış hedeflenmiyor).

Önerilen sıra:

1. E1 contract + exact baseline;
2. E2 canonical inversion + adapter;
3. identity/parity tests;
4. full verification;
5. independent review.

`task_state_context.py` için ayrı migration planı ve ayrı caller audit'i
hazırlanmadan onun implementasyonuna geçilmez. Bu plan yalnız task model
inversion'ını tanımlar ve hiçbir `.py` production dosyasını değiştirmez.

## 10. Plan verdict

**PLAN ACCEPTANCE STATUS: REVIEW PENDING**

`task_model.py` davranış olarak sıfır etkili bir adapter inversion ile
taşınabilir; ancak HIGH blast radius nedeniyle bu belge implementasyon onayı
değildir. İnsan/bağımsız review onayı olmadan E1 dışındaki hiçbir adım
başlatılmamalıdır.
