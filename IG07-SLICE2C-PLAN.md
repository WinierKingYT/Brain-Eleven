# IG-07 Slice 2C — Canonical Migration Tools Plan

**Durum:** PLAN ONLY / IMPLEMENTATION NOT AUTHORIZED  
**Program:** Intelligence Graduation  
**Slice:** IG-07 / Slice 2C  
**İncelenen revision:** `fbcd16348031047c40c20db69b6c565216e058eb` (`origin/master`)  
**Kapsam:** `dedupe-validated-memory.py`, `migrate-legacy-memory.py`, `migrate-memory-scope.py`

## 0. Bu belgenin sınırı

Bu belge yalnızca envanter, risk analizi, bounded migration contract ve kanıt planıdır. Bu turda hiçbir `.py` dosyası değiştirilmez; migration implementasyonu, adapter yazımı, test davranışı değişikliği, dosya silme veya Phase 20 çalışması başlatılmaz.

Slice 2A ve 2B'deki read-only/derived projection taşımalarından farklı olarak bu üç araç canonical memory verisine dokunur veya veriyi dönüştürür. Bu nedenle yalnızca “implementasyonu package'a kopyala, script'i adapter yap” yaklaşımı yeterli kabul edilmez. Canonical yazım, idempotence, backup, rollback, revision ve concurrency kanıtları implementasyondan önce contract olarak kilitlenmelidir.

Aşağıdaki sınırlar bu slice'ın dışındadır:

- `MemoryStore`, `StateStore` ve `ProjectRegistry` implementasyonunun değiştirilmesi;
- `remember.py`, `task_state_context.py`, capture/retrieval yolları;
- yeni persistence authority veya yeni bir canonical write path;
- Phase 20, V2 promotion ve unrelated feature çalışması;
- sıfır caller'lı araçların sessizce silinmesi.

## 1. Mevcut canonical yazım sözleşmesi

Üç aracın ortak güvenlik zemini mevcut `MemoryStore` yüzeyidir. `brain_eleven.memory` package yüzeyi, `brain_eleven/memory/store.py` üzerinden legacy store implementasyonunu expose eder; bu slice store'un kendisini yeniden yazmayı hedeflemez.

### 1.1 `MemoryStore.transact`

`scripts/memory_store.py` içindeki mevcut akış:

- `transact` yaklaşık 158–177. satırlarda `memory_store_lock` ile exclusive lock alır;
- canonical dosyayı lock altında yeniden yükler;
- `expected_revision` verilmişse mevcut revision ile karşılaştırır ve stale input'ı reddeder;
- mutator sonucunu normalize eder, değişiklik yoksa yazmayı atlar;
- revision/schema/update zamanı güncellenir ve `_write_unlocked` çağrılır.

`replace` yaklaşık 179–195. satırlarda aynı transaction yolunu kullanır; mevcut revision, schema ve operation receipt bilgileri korunur. Migration modülleri bu yüzeyleri çağırmalı, canonical JSON'a doğrudan `open(..., "w")`, `json.dump` veya `os.replace` yapmamalıdır.

### 1.2 Atomic write ve backup

`_write_unlocked` yaklaşık 131–156. satırlarda:

1. normalize edilmiş payload'ı hazırlar;
2. mevcut canonical dosyayı `validated-memory.backup.json` olarak kopyalar;
3. aynı dizinde temporary file oluşturur;
4. JSON yazıp `flush` + `fsync` yapar;
5. `replace` ile canonical dosyayı atomik olarak değiştirir;
6. temporary file temizliğini yapar.

Bu fixed backup davranışı `MemoryStore` seviyesinin invariant'ıdır. Scope migration ayrıca kendi migration öncesi timestamp'li backup'ını üretir; iki backup türünün sorumluluğu karıştırılmamalıdır.

## 2. Script envanteri

Satır numaraları bu planın incelendiği `fbcd163` revision'ına aittir; implementasyon öncesi diff değişirse yeniden doğrulanacaktır.

| Script | Boyut | Son değişiklik | Canonical yazım | Caller sonucu |
|---|---:|---|---|---|
| `scripts/dedupe-validated-memory.py` | 112 fiziksel / 91 nonblank / 89 noncomment satır | `ea0dd16` — 2026-09-06 | `MemoryLifecycleManager.supersede_memory` → `manager.save()` → `MemoryStore.replace(expected_revision=...)` | **0 production / 0 behavioral test** |
| `scripts/migrate-legacy-memory.py` | 93 fiziksel / 72 nonblank / 71 noncomment satır | `bd90a55` — 2026-09-06 | `MemoryStore.transact(mutate)`; caller-level `expected_revision` yok | **0 production / 0 behavioral test** |
| `scripts/migrate-memory-scope.py` | 251 fiziksel / 212 nonblank / 211 noncomment satır | `bd90a55` — 2026-09-06 | `MemoryStore.transact(mutate)`; rollback `MemoryStore.replace(...)` | **0 production / 2 behavioral test** |

Caller sayımı yalnız gerçek import/dynamic load/function call'ları kapsar. Docstring, documentation listesi, coverage exclusion ve static inventory string'leri runtime caller sayılmaz.

### 2.1 `dedupe-validated-memory.py`

- 41. satır `MemoryLifecycleManager` import eder.
- 49. satır `plan_dedupe` tanımlar.
- 51–72. satırlar `dedup_fingerprint` ile gruplar; aktif kayıtları superseded olmayanlar arasından seçer, timestamp'e göre sıralar ve ilk kaydı koruyup kalanları loser olarak üretir.
- 75–80. satırlar `--apply` ve vault argümanını çözer; varsayılan vault home altındadır.
- 80. satır lifecycle manager oluşturur.
- 101–105. satırlar `--apply` durumunda loser kayıtları `manager.supersede_memory` ile işaretler, ardından `manager.save()` çağırır.

Bu script dosyaya doğrudan yazmaz. `scripts/memory-lifecycle.py` içindeki `save` yaklaşık 175–184. satırlarda `self.store.replace(data, expected_revision=self.store_revision)` çağırır. Dolayısıyla lock, CAS ve atomic backup canonical `MemoryStore` üzerinden gelir; ancak dedupe'nin kendi planlama snapshot'ı ile save anı arasındaki stale-window ve eşit timestamp tie-break davranışı ayrıca contract edilmelidir.

**Kullanım sorusu:** production ve behavioral test caller'ı sıfırdır. `tests/test_pre12_memory_state_caller_migration.py:115-117` yalnız static `LIFECYCLE_CALLERS` envanteridir; `.coveragerc` one-off cleanup olarak exclude eder; `CODEX-RESULTS.md` operasyonel CLI olarak listeler. Bu veriler “ölü kod” ihtimalini güçlü biçimde gösterir fakat tek başına silme yetkisi vermez. Uygulama öncesi Ahmet'in C0 kararı gerekir: korunup package'a taşınacak mı, tarihsel/operasyonel adapter olarak mı tutulacak, yoksa ayrı bir retirement/deletion planına mı ayrılacak? Bu plan karar vermemekte, kararı görünür bir gate olarak bırakmaktadır.

### 2.2 `migrate-legacy-memory.py`

- 19. satır `MemoryStore`, `infer_memory_scope` ve `scoped_fingerprint` import eder.
- 32–34. satırlar type-aware fingerprint hesaplar.
- 37–38. satırlar `migrate_legacy_memory` fonksiyonunu tanımlar.
- 40–42. satırlar store ve canonical/fixed backup yollarını hazırlar.
- 44–46. satırlar canonical dosya yoksa no-op döner.
- 48–71. satırlar validated/rejected bucket'larını gezer; eksik ID, scope, project metadata, fingerprint ve source id alanlarını doldurur.
- 69–70. satırlar her migration çalışmasında `migrated_at=datetime.now().isoformat()` ve `migration_version="1.0"` yazar.
- 73. satır `store.transact(mutate)` çağırır.
- 75–78. satırlar fixed backup yolunu raporlar; 83–93. satırlar direct CLI'dır.

Bu araç da doğrudan dosyaya yazmaz; lock ve atomic write `MemoryStore.transact` içindedir. Ancak caller-level `expected_revision` kullanmadığı için external snapshot/CAS contract'ı yoktur. Daha kritik bulgu, mevcut `migrated_at` atamasının ikinci çalıştırmada değişebilmesidir. Bu haliyle “veri alanları aynı kaldı” idempotence iddiası zayıftır; implementation öncesi contract, metadata'nın yalnız ilk gerçek dönüşümde yazılmasını veya eşdeğer no-change davranışını zorunlu kılmalıdır. Bu plan mevcut davranışı sessizce değiştirmez; bug/contract kararı C2 implementasyonunda açıkça kanıtlanmalıdır.

**Kullanım sorusu:** production ve behavioral test caller'ı sıfırdır. `tests/test_pre12_memory_state_caller_migration.py:146-149` static `LEGACY_MIGRATION_CALLERS` listesidir; `.coveragerc` one-off migration olarak exclude eder; `CODEX-RESULTS.md` CLI'yi listeler. Bu araç için de C0 insan kararı olmadan “taşı” veya “sil” kararı verilmeyecektir.

### 2.3 `migrate-memory-scope.py`

- 17–25. satırlar package memory yüzeylerini import eder; 28. satır `MIGRATION_NAME="scope-v2"` tanımlar.
- 31. satır `MemoryScopeMigrationError` tanımlar.
- 39–45. satırlar migration öncesi `shutil.copy2` ile timestamp'li `.pre-scope-v2-<stamp>.bak` üretir.
- 48–51. satırlar raw JSON okuyarak schema upgrade gereksinimini kontrol eder.
- 69–115. satırlar candidate document üretir, değişiklikleri sayar, ambiguity'yi işaretler ve çözülemeyen kayıtları korur.
- 141–148. satırlar `migrate` girişini ve missing-file davranışını kurar.
- 149–161. satırlar dry-run'da lockless load/candidate üretir; canonical write yapmaz.
- 163–196. satırlar `MemoryStore.transact` mutator'ı içinde değişiklikleri uygular; 186. satırda exact pre-scope backup alınır; 198. satır transact; 199. satır sonucu revision ile döner.
- 203–228. satırlar `rollback` backup'ı doğrular, JSON'u normalize eder ve `store.replace(deepcopy(normalized_backup))` ile geri yükler; caller-level expected revision yoktur.
- 231–251. satırlar `--dry-run` ve `--rollback BACKUP` dahil CLI yüzeyidir.

Bu scriptin gerçek davranış caller'ları iki test yüzeyidir: `tests/test_memory_scope_migration.py:21-28` dynamic loader ile 7 test, `tests/test_phase14_scope.py:250-251` içindeki `test_migration_is_idempotent_and_preserves_identity`. Production caller yoktur; `CLAUDE.md:69` yalnız operasyonel referanstır. Current test adı idempotence'i hedeflese de implementasyon planı payload, backup, revision ve identity'nin ayrı ayrı ölçülmesini istemelidir.

### 2.4 Risk sınıflandırması

Üç modül de **HIGH risk** olarak kalır. Düşük caller sayısı riski düşürmez; canonical memory'ye yazma, veri dönüşümü, backup ve rollback blast radius'u caller sayısından bağımsızdır.

- `dedupe-validated-memory.py`: **HIGH** — lifecycle supersession ile birden fazla canonical kaydı aynı transaction'da etkiler; yanlış winner seçimi veya stale snapshot yanlış memory'yi supersede edebilir.
- `migrate-legacy-memory.py`: **HIGH** — validated/rejected kayıtlarının shape ve provenance alanlarını topluca değiştirir; bugün doğrudan test caller'ı olmaması regresyon gözlemlenmesini daha da zayıflatır.
- `migrate-memory-scope.py`: **HIGH** — scope/project alanlarını topluca dönüştürür ve rollback yapar; mevcut behavioral testleri olsa da cross-project isolation ve concurrent rollback ayrıca kanıtlanmalıdır.

Bu sınıflandırma Slice 1/2A/2B'deki read-only projection modülleri için kullanılan düşük/orta risk varsayımını bu üç araca taşımamayı zorunlu kılar.

## 3. Shared package hedefi ve namespace contract

### 3.1 Hedef topology

Önerilen hedef:

```text
brain_eleven/
  lifecycle/
    dedupe.py              # yalnız dedupe plan/apply projection
  memory/
    migrations.py          # legacy migration + scope migration/rollback
```

`dedupe-validated-memory.py` lifecycle davranışına aittir; `migrations.py` içine alınmayacaktır. `migrate-legacy-memory.py` ve `migrate-memory-scope.py` aynı `brain_eleven.memory.migrations` modülünde birlikte yaşar, fakat açık isim uzayları kullanır:

- `migrate_legacy_memory(...)` — legacy shape/metadata migration;
- `migrate_scope(...)` — scope-v2 candidate/apply entry point;
- `rollback_scope(...)` — scope backup rollback entry point;
- `SCOPE_MIGRATION_NAME` ve `MemoryScopeMigrationError` — scope'a özel semboller.

Generic `migrate` veya generic `rollback` export'u oluşturulmayacak; böylece iki migration'ın birbirini gölgelemesi engellenecek. Her function kendi result type/operation label'ını taşımalı ve `migration_version`/`MIGRATION_NAME` değerleri karışmamalıdır. Legacy migration'ın mevcut callable adı package yüzeyinde korunabilir; scope için adapter compatibility alias'ları yalnız açıkça `migrate` ve `rollback` CLI anlamında, module-local olarak kalmalıdır.

### 3.2 Adapter yönü

Her script, Slice 1/2A/2B'deki `_load_canonical` desenine benzer biçimde:

1. repo root için minimal `sys.path` ayarı yapar;
2. package module'ünü bir kez yükleyip cache'ler;
3. public constant/function/error sembollerini re-export eder;
4. mevcut direct-execution CLI argümanlarını ve bare-module alias'ını korur;
5. kendi içinde canonical write, migration mutator veya duplicate persistence mantığı tutmaz.

Adapter dosyasındaki compatibility alias'ları, package fonksiyonlarına işaret eden aynı object identity'yi göstermelidir. Legacy scriptlerin operational invocation'ı korunur; package implementasyonu script'i import etmez.

### 3.3 Sıfır caller kararı bir implementation ön koşuludur

`dedupe` ve `legacy` için C0 gate üç olası sonucu açıkça kayda geçirir:

1. **Retain and migrate:** package implementation + thin adapter + direct CLI;
2. **Archive as historical/operational:** production package'a taşımadan yalnız belgelenmiş bakım aracını koruma;
3. **Retire:** ayrı bir deletion/archive contract, migration evidence ve user approval sonrasında.

Bu Slice 2C planı seçenekler arasından seçim yapmaz. “Caller yok” bulgusu production kullanımının kanıtlanmadığını söyler; silme yetkisi vermez.

## 4. Korunacak invariant'lar

### 4.1 Canonical authority, lock ve CAS

- Hiçbir migration canonical JSON'a doğrudan yazmayacak.
- Apply yolu `MemoryStore.transact` veya `replace` üzerinden lock + normalize + revision increment + atomic replace kullanacak.
- Dedupe lifecycle save'i mevcut `expected_revision` davranışını koruyacak; snapshot ile commit arasında canonical revision değişirse açık conflict/stale sonucu üretilecek.
- Legacy migration için caller-level CAS eklenmesi gerekiyorsa bu bounded contract/test ile yapılacak; “son yazan kazanır” sessiz davranış kabul edilmeyecek.
- Scope rollback da current revision'ı gözlemleyip conflict davranışını belgeleyecek; rollback'ın eski payload revision'ını körlemesine geri alması kabul edilmeyecek. Revision monotonic kalmalı.

### 4.2 Idempotence

Aynı migration aynı canonical input üzerinde iki kez çalıştırıldığında:

- memory içerikleri, IDs, fingerprints, scope/project alanları ve lifecycle state değişmemeli;
- ikinci çalıştırma no-op sonucu vermeli veya açıkça `already_migrated` bildirmeli;
- revision gereksiz yere artmamalı;
- backup sayısı ve backup semantiği contract'ta tanımlı olmalı;
- operation receipt varsa aynı operation'ın duplicate etkisi canonical memory üretmemeli.

Özellikle legacy migration'daki mevcut her-run `migrated_at` yazımı bu gate'i bugün karşılamayabilir. Bu, planın bilerek görünür kıldığı ilk potansiyel implementation blocker'ıdır; test ile kanıtlanmadan “idempotent” denmeyecektir.

### 4.3 Integrity ve backup

- Migration öncesi ve sonrası canonical records için count, ID seti, fingerprint seti, scope dağılımı ve lifecycle durumları karşılaştırılmalı.
- Mevcut fixed `validated-memory.backup.json` üretimi korunmalı.
- Scope migration'ın timestamp'li `.pre-scope-v2-<stamp>.bak` dosyası migration öncesi raw payload'ın byte/semantic bütünlüğünü taşımalı.
- Backup yazılamazsa canonical write başlamamalı ve hata görünür olmalı.
- Corrupt, yanlış schema veya başka vault'a ait backup reddedilmeli; sessiz normalize ile veri kaybı kabul edilmemeli.

### 4.4 Rollback

Rollback yüzeyi yalnız “function mevcut” diye doğrulanmış sayılmayacak. Kanıt:

1. migration sonrası payload'ın backup ile geri alınması;
2. restore sonrası IDs/fingerprints/scope/lifecycle ve operation receipt karşılaştırması;
3. restore işleminde yeni canonical revision üretilmesi ve revision'ın geriye gitmemesi;
4. invalid/missing/corrupt backup'ın açık hata vermesi;
5. concurrent writer/stale revision durumunda rollback'ın sessiz overwrite yapmaması;
6. ikinci rollback'in idempotent veya açıkça guarded olması.

## 5. Sıralama önerisi

Üçünü aynı anda taşımak önerilmez. Bounded adımlar:

### C0 — Usage and retirement decision

Önce Ahmet, sıfır caller'lı dedupe ve legacy araçları için “retain/migrate”, “archive” veya “retire” kararını verir. Karar yoksa yalnız scope migration planlanabilir; production write taşımasına başlanmaz.

### C1 — Dedupe (conditional lowest blast radius)

Caller'sız olsa da kapsamı en dar olan dedupe önce gelir. Dedupe yalnız lifecycle supersession projection'ı olduğundan migration package'ından ayrı tutulur. Ön koşul, snapshot/CAS conflict, equal timestamp deterministic tie-break ve apply/replay kanıtıdır. C1 review olmadan C2 açılmaz.

### C2 — Legacy shape migration

Legacy migration, scope migration'dan önce ele alınır; çünkü scope-v2 candidate'ı eksik legacy metadata üzerinde çalıştırılmamalıdır. C2'de idempotence ve `migrated_at` semantiği açıkça çözülür, sonra canonical package surface'e alınır.

### C3 — Scope migration + rollback

En yüksek mevcut behavioral coverage ve en geniş data transformation yüzeyi scope migration'dadır. C2'nin normalized legacy output'u ile C3 test fixture'ları ayrılır. C3'ün rollback/concurrency kanıtı tamamlanmadan Slice 2C kapanmaz.

Bu sıra “dedupe her durumda ilk implementasyon” anlamına gelmez; C0 usage kararına bağlıdır. Her adımın sonunda bağımsız review gerekir.

## 6. Mevcut test ve caller kanıtı

### 6.1 Scope migration mevcut testleri

- `tests/test_memory_scope_migration.py`: 7 test; dynamic module loader, migration candidate, dry-run, backup, malformed/ambiguous input ve rollback davranışlarını kapsar.
- `tests/test_phase14_scope.py::test_migration_is_idempotent_and_preserves_identity`: 1 test; idempotence ve identity beklentisi.
- `tests/test_pre12_memory_state_caller_migration.py`: static caller-boundary inventory; runtime caller değildir ama migration surface'in package authority'sini kontrol eden regression contract'tır.

### 6.2 Canonical store/lifecycle regression yüzeyleri

- `tests/test_memory_store.py`: transaction, backup, concurrency/stale revision, corrupt payload ve no-change davranışları için 5 ilgili test.
- `tests/test_memory_lifecycle.py`: lifecycle manager save/supersede davranışları için 12 test.
- `tests/test_memory_backup.py`: backup/restore için 8 test.
- `tests/test_memory_validator.py`: fingerprint/dedup ve record validation yüzeyi.
- `tests/test_phase14_scope.py`: scope izolasyonu ve migration integration.

### 6.3 Yeni migration contract testleri

Her bounded implementation için production davranışına ek olarak şu testler planlanır:

1. package/script/bare-module object identity;
2. adapter-only AST: class, mutator, direct JSON write ve duplicate persistence yok;
3. `--dry-run` hiçbir canonical effect üretmez;
4. apply → replay idempotence;
5. pre/post integrity fingerprint ve ID set karşılaştırması;
6. fixed/timestamp backup üretimi ve backup failure fail-closed;
7. stale revision/CAS conflict ve lock timeout visibility;
8. crash injection: backup sonrası, canonical write öncesi/sonrası, receipt öncesi;
9. rollback restoration, monotonic revision ve invalid backup rejection;
10. project/scope isolation ve cross-project non-leakage;
11. direct CLI parity ve exit code/output contract.

Dedup için ayrıca equal timestamp + duplicate fingerprint deterministic winner, already-superseded record protection ve apply/replay canonical effect testleri gerekir. Legacy için missing ID/scope/fingerprint, preserved user fields, no-op rerun ve migration version testleri gerekir. Scope için existing 8 testin davranışı değiştirilmeden yeni rollback/CAS/concurrency assertions eklenir.

## 7. Beş kapılı acceptance planı

Her sub-package aşağıdaki beş kapıdan geçer:

1. **Authority/identity:** package, adapter ve bare-module isimleri aynı canonical function/class/constant objelerine çözülür; canonical `MemoryStore` authority'si değişmez.
2. **Adapter-only:** AST ve runtime inspection ile script'te ikinci implementation, doğrudan file write, duplicate mutator veya `scripts.*` içinden package import yönü tespit edilmez.
3. **Parity + safety:** mevcut testler değişmeden geçer; idempotence, integrity, rollback, CAS/lock, crash/replay ve scope isolation yeni contract testleriyle ölçülür.
4. **Full verification:** ilgili focused suite, `pytest tests -q`, critical flake8 (`E9,F63,F7,F82`) dokunulan dosyalarda, `compileall`, import sanity ve `git diff --check` çalışır. Plan-only turda bunlar çalıştırılmayacaktır; yalnız implementation turunun exit evidence'ıdır.
5. **Independent review:** implementer kendine SHIP veremez. Diff, canonical write path, data-loss failure modes, backup/rollback evidence ve caller decision ayrı read-only reviewer tarafından incelenir.

Her gate exact revision, command, exit code ve artifact path ile raporlanmalıdır. “Testler geçti” veya “adapter gibi görünüyor” tek başına evidence sayılmaz.

## 8. Tahmini değişiklik boyutu

Tahminler mevcut script boyutları ve Slice 1/2A/2B migration desenine göredir; generated test/evidence dosyaları dahil değildir:

| Bounded adım | Production/package + adapter | Contract/parity tests | Tahmini toplam |
|---|---:|---:|---:|
| C1 dedupe | 150–230 satır | 120–190 satır | 270–420 satır |
| C2 legacy migration | 120–190 satır | 130–210 satır | 250–400 satır |
| C3 scope + rollback | 260–380 satır | 220–340 satır | 480–720 satır |
| Slice 2C docs/evidence | 80–140 satır | — | 80–140 satır |

Toplam uygulama tahmini **1.080–1.680 satır** aralığındadır. Bu geniş aralık, özellikle rollback/concurrency/crash injection kanıtlarının mevcut davranışı açıklığa kavuşturmasına bağlıdır. LOC hedef değildir; gereksiz yeniden yazım veya canonical authority kopyası kabul edilmez.

## 9. Slice 2C çıkış kapısı

Slice 2C ancak aşağıdakilerin hepsi sağlanırsa review'a sunulabilir:

- C0 zero-caller usage/retirement kararı yazılı;
- her scriptin exact current write path ve caller listesi revision-bound;
- dedupe/legacy/scope package authority'si açık ve namespace çakışması yok;
- migration replay idempotence kanıtı;
- pre/post integrity ve backup kanıtı;
- scope rollback gerçekten çalışıyor ve monotonic revision koruyor;
- CAS/lock/atomic write canonical `MemoryStore` üzerinden doğrulanıyor;
- project/scope isolation ve corruption fail-closed davranışı korunuyor;
- existing migration tests değişmeden geçiyor;
- full regression, critical lint, compile/import ve diff checks yeşil;
- bağımsız reviewer sonucu yalnız `SHIP`, `FIX-FIRST` veya `RETHINK` olarak veriliyor.

Bu planın tamamlanması implementasyon izni değildir. Ahmet'in bounded contract/onayı ve her alt dilim için bağımsız review olmadan production `.py` dosyasına dokunulmayacaktır.

## 10. Package report için zorunlu alanlar

İleride her alt dilim raporu şunları içermelidir:

```text
PACKAGE:
REVISION:
OBJECTIVE:
FILES CHANGED:
WRITE PATH / AUTHORITY:
CALLER DECISION:
ROLLBACK / IDEMPOTENCE EVIDENCE:
TESTS ADDED:
TESTS EXECUTED:
INTEGRITY / SAFETY METRICS:
KNOWN LIMITATIONS:
OPEN FAILURES:
INDEPENDENT REVIEW:
VERDICT: SHIP / FIX-FIRST / RETHINK
```

**Plan status:** REVIEW PENDING — implementation başlamadı.
