# IG-07 Slice 2D — Global Installer ve Manual Capture Planı

**Durum:** PLAN ONLY / IMPLEMENTATION NOT AUTHORIZED  
**Program:** Intelligence Graduation  
**Slice:** IG-07 / Slice 2D  
**İncelenen revision:** `2ae9aec4c567298a8e70981b3bd4140272b7a32d` (`origin/master`)  
**Kapsam:** `scripts/install-cross-project-memory.py`, `scripts/remember.py`

## 0. Sınır ve karar sırası

Bu belge yalnızca gerçek runtime envanteri, bounded package contract, risk analizi ve acceptance kanıtı planıdır. Bu turda hiçbir production `.py` dosyası değiştirilmeyecek, package implementasyonu oluşturulmayacak ve installer/capture davranışı değiştirilmeyecektir.

Slice 2D iki farklı risk yüzeyini aynı plan içinde ama ayrı bounded bölümlerde ele alır:

- **Bölüm A — global installer:** vault dışındaki gerçek kullanıcı Claude/Codex configuration dosyalarına yazan host-filesystem mutasyonu;
- **Bölüm B — remember:** canonical `MemoryStore` transaction sınırından geçen manual capture ve project/scope policy.

Bu slice'ın dışında:

- `task_state_context.py`, `task_model.py`;
- `MemoryStore`, `ProjectRegistry` ve `brain_eleven/runtime/install.py` implementasyonlarının yeniden yazılması;
- capture hook/worker, retrieval, V2 promotion ve Phase 20;
- `migrate-legacy-memory.py`, `migrate-memory-scope.py` ve C1 dedupe davranışının yeniden açılması.

Implementation ancak bu plan bağımsız incelenip bounded contract olarak onaylandıktan sonra başlayabilir.

## 1. Ortak mevcut durum ve caller doğrulaması

| Script | Mevcut boyut | Son görülen değişiklik | Gerçek caller durumu | Risk |
|---|---:|---|---|---|
| `scripts/install-cross-project-memory.py` | 371 fiziksel satır | `8f7dab8` — 2026-09-02 | 0 production / 1 test modülü (`tests/test_phase14_scope.py`, 8 dynamic-loader senaryosu) | HIGH — host config mutasyonu |
| `scripts/remember.py` | 219 fiziksel satır | `38b9728` — 2026-09-11 | 1 production (`scripts/remember_opt_in.py`) / 2 behavioral test modülü (`tests/test_remember.py`, `tests/test_capture_safety.py`) | HIGH — canonical capture |

Caller sayımı gerçek import/dynamic-loader/function call'larını içerir. Dokümantasyon, template komutu ve `tests/test_pre12_memory_state_caller_migration.py` içindeki static inventory string'leri ayrı operational evidence olarak kaydedilir; behavioral caller sayılmaz.

### 1.1 Installer caller bulgusu

`install-cross-project-memory.py` için repository içinde production import veya function call bulunmadı. `tests/test_phase14_scope.py` sekiz ayrı dynamic-loader senaryosuyla installer'ı doğrudan yükler:

- unrelated settings preservation + reversible uninstall;
- successful reinstall idempotence;
- matching partial legacy install recovery;
- user conflict fail-closed;
- legacy artifact upgrade backup;
- manifest-owned artifact upgrade;
- Windows Git Bash/WSL hook path rendering;
- exact legacy hook command replacement.

`CLAUDE.md:71` CLI kullanımını belgeler; `CODEX-RESULTS.md:43` operasyonel script listesinde tutar. Bunlar kullanım niyetini gösterir, canlı başka makinelerde gerçekten çalıştırıldığına dair telemetry değildir.

**C0 operational-use gate:** Ahmet, bu installer'ın başka makinelerde/projelerde aktif kurulum aracı olarak tutulacağını mı, yoksa historical/manual migration tool olarak mı kalacağını açıkça seçmelidir. Production caller sayısının sıfır olması tek başına silme veya package'a taşıma yetkisi vermez. Seçenekler: `retain and migrate`, `archive as operational legacy`, veya ayrı deletion/retirement contract. Bu plan seçim yapmaz.

### 1.2 Remember caller bulgusu

`scripts/remember_opt_in.py:9` `proactive_capture_policy` import eder ve CLI opt-in kararını sunar; bu tek production Python caller'ıdır. `templates/claude/commands/remember.md` ve `templates/claude/legacy/remember-v1.md` script CLI'sini shell üzerinden çalıştırır, Python import caller değildir.

Behavioral coverage:

- `tests/test_remember.py`: capture, project dedup isolation, registry relocation, opt-in policy, legacy opt-in migration, archived/unknown project ve CLI davranışları;
- `tests/test_capture_safety.py`: unsafe secret/transcript/large payload rejection ve persistence öncesi fail-closed safety;
- `tests/test_pre12_memory_state_caller_migration.py:143` static manual-capture inventory; runtime caller değildir.

Remember için production kullanımı vardır, fakat orchestration hâlâ hyphenated script ve legacy validator üzerinde durmaktadır. Bu nedenle migration daraltılmış capture facade olmalı, validator/store authority'sini kopyalamamalıdır.

# Bölüm A — `install-cross-project-memory.py`

## A1. Mevcut mekanizma ve yazdığı dosyalar

Bu script `scripts/install-cross-project-memory.py:217-314` aralığında global Claude integration yönetir. `brain_eleven/runtime/install.py` ile aynı `install` adına sahip olsa da aynı state'i yönetmez.

### A1.1 Scriptin dosya envanteri

`install(home, vault, dry_run=False)` şu yolları hesaplar:

- `home/.claude/commands/remember.md` (`:221-225`);
- `home/.claude/hooks/brain-eleven-session-start` (`:221-225`);
- `home/.claude/hooks/brain-eleven-remember-opt-in` (`:221-225`);
- `home/.claude/settings.json` (`:218-220`) — yalnız exact managed SessionStart/SessionEnd command entries eklenir veya çıkarılır;
- `home/.claude/.brain-eleven-install.json` (`MANIFEST_NAME`, `:25`, `:220`) — managed file hash'leri, vault ve settings command kayıtları.

Template dosyaları `templates/claude` ve `templates/claude/legacy` altından okunur (`:22-24`, `:175-180`). Vault yolu template içine `_shell_path` ile shell-quoted olarak yerleştirilir (`:32-39`). Installer doğrudan canonical memory'ye yazmaz.

### A1.2 “Yalnız kendi dosyaları” iddiasının kod kanıtı

- New/upgrade write'ları yalnız `file_specs` içindeki üç path'e gider (`:221-225`, `:283-295`).
- Existing managed file, manifest hash'i veya bilinen legacy template ile eşleşmiyorsa `conflict` üretilir (`:232-255`); preflight tamamlanmadan settings/manifest/new file yazılmaz.
- Settings hook removal yalnız `_legacy_settings_commands()` ve manifest'ten trusted `settings_commands` setiyle yapılır (`:100-129`, `:266-281`, `:337-345`). Unrelated hook groups korunur.
- Upgrade öncesi managed file ve settings backup'ları `_backup_managed_file`/`_backup_settings` ile alınır (`:71-82`, `:289-303`, `:343-345`).
- Uninstall yalnız manifest `files` kayıtlarında hash'i hâlâ eşleşen dosyaları siler; değiştirilmiş dosyaları `skipped_modified` olarak bırakır (`:323-335`).
- `main` conflict veya skipped-modified durumunu non-zero exit ile bildirir (`:353-367`).

Bu iddialar testlerle kısmen kanıtlanmış olsa da manifest'in kendisi ayrıca doğrulanmalıdır: `uninstall` manifestteki path'leri doğrudan `Path(path_text)` olarak kullanıyor (`:325`). Mevcut kodda bu path'in `home/.claude` altında olduğunu doğrulayan containment kontrolü yoktur. Manifest dışarıdan değiştirilmişse host filesystem path traversal/unauthorized deletion riski oluşabilir. Bu, implementation öncesi A-Security gate'idir; sessizce “güvenli” kabul edilmeyecektir.

### A1.3 Atomicity ve dry-run

- Text file write'ları temp file + flush/fsync + replace ile yapılır (`:56-69`).
- JSON settings/manifest write'ları temp file + replace ile yapılır (`:42-54`); JSON writer'da ayrıca fsync kanıtı yoktur ve bu sınırlılık raporlanmalıdır.
- `dry_run` mevcut files/settings'i okur, memory'de plan üretir, fakat `:283`, `:300-312`, `:334-349` write bloklarını çalıştırmaz. Testte byte-level hiçbir filesystem değişikliği, yeni directory veya backup oluşmadığı kanıtlanmalıdır.

### A1.4 Uninstall davranış sınırı

Uninstall değiştirilmiş managed file'a dokunmaz; fakat manifest değişse bile güvenilirlikte temel alınır ve başarılı non-dry-run uninstall sonunda manifesti siler (`:348-350`). Bu davranışın kullanıcıya açık sonucu contract'a yazılmalıdır: modified files remain, `skipped_modified` evidence is retained in result, manifest removal is intentional and independently reviewed. Manifest invalid/corrupt/path-outside-home ise uninstall fail-closed olmalı; mevcut raw `json.loads`/unvalidated path davranışı implementation gate'inde yeniden değerlendirilecektir.

## A2. Runtime installer ile overlap analizi

`brain_eleven/runtime/install.py` bağımsız bir native client installer'dır:

- `client_paths` (`:41-44`) Claude `home/.claude/settings.json`, Codex ise `$CODEX_HOME/hooks.json` veya `home/.codex/hooks.json` döndürür;
- `EVENTS` (`:13`) SessionStart, UserPromptSubmit, Stop, SessionEnd'in tamamını yönetir;
- `hook_command` (`:17-28`) `brain_eleven/runtime/launcher.py` ve windowless Python/PowerShell/Bash command'larını üretir;
- `merge_hooks`, `remove_owned`, `owned_entries` (`:31-58`) native manifestte journaled owned entries tutar;
- `install` (`:94-164`) vault-local `.brain-eleven/runtime/installation.json`, `native-hooks-installed.json`, RuntimeConfig mode/project ids, ProjectRegistry opt-in ve StateService initialization'ını birlikte yönetir;
- `uninstall` (`:166-185`) mode'u OFF yapar, service'i durdurur, journaled client entries'i kaldırır ve legacy entries'i restore eder.

İki mekanizma arasında:

- **Aynı dosya:** Claude `settings.json` üzerinde overlap vardır.
- **Farklı entries:** cross-project script yalnız SessionStart/SessionEnd shell hook'larını (`:161-165`) yönetir; runtime installer native launcher entry'lerini dört event için yönetir.
- **Farklı state:** cross-project manifest `home/.claude/.brain-eleven-install.json`; runtime manifest `vault/.brain-eleven/runtime/installation.json` ve `native-hooks-installed.json`.
- **Farklı ownership:** cross-project script template command/hook dosyalarını da yazar; runtime installer host config entry'leri ve vault runtime state'ini journal'lar.
- **Tamamlayıcı ama aynı config dosyasında rakip write riski:** iki installer birbirinin entry formatını exact equality ile tanımayabilir. Birleştirme kararı verilmeden önce aynı home üzerinde sırayla install/uninstall matrix'i gerekir.

Sonuç: Bunlar isim benzerliğinden ibaret değildir; Claude settings üzerinde gerçek bir ortak yazma yüzeyi vardır. Ancak aynı installer authority'si değiller. A planı `runtime/install.py` içine kod kopyalamayı veya onu değiştirmeyi önermemektedir. Önerilen package hedefi, ayrı bir `brain_eleven/runtime/global_install.py` canonical module'üdür; native installer `brain_eleven/runtime/install.py` olarak kalır.

## A3. Installer migration contract

### A3.1 Package/adaptor sınırı

`brain_eleven/runtime/global_install.py` şu sembolleri sahiplenmelidir: `MANIFEST_NAME`, `install`, `uninstall`, `main` ve gerekli deterministic helper'lar. `scripts/install-cross-project-memory.py`:

1. package module'ünü bir kez load/cache eder;
2. public helper/API ve `MANIFEST_NAME` re-export eder;
3. direct CLI argümanlarını korur;
4. hiçbir template render, settings mutation, backup veya manifest mutator implementasyonu içermez;
5. eski dynamic loader/bare-module compatibility yüzeyini korur.

`brain_eleven/runtime/install.py` bu package'a import edilmez ve onun implementation'ı kopyalanmaz. İki module'un ortak helper ihtiyacı olursa yalnız açık, read-only path/entry utility contract'ı ile paylaşılır; ownership belirsiz bir “combined installer” oluşturulmaz.

### A3.2 Host safety invariants

- `home`, `vault` ve template root path'leri resolve edilir; template dışı source path okunmaz.
- Rendered hook commands shell injection olmadan quote edilir; vault path newline/quote/drive/UNC/WSL varyantlarında parity testinden geçer.
- Managed file path'leri `home/.claude` containment ile doğrulanır; manifest'ten gelen uninstall path'i containment dışındaysa fail-closed olur.
- Manifest schema/version/vault identity/files/settings_commands türleri doğrulanmadan uninstall mutation yapmaz.
- Install tüm managed-file conflict'lerini preflight eder; partial write başlamadan önce conflict döner.
- Re-install semantic olarak idempotenttir: managed file bytes, settings unrelated entries ve manifest ownership aynı kalır; gereksiz settings backup üretilmez.
- Uninstall yalnız hash'i eşleşen Brain-Eleven-owned files/commands'ı kaldırır; user-modified file/hook preserved ve result'ta görünür olur.
- Dry-run hiçbir file, directory, backup, manifest veya settings byte'ı değiştirmez.
- Her write atomic olur; crash/partial install sonrası manifest journal recovery test edilir.

### A3.3 C0 usage gate ve ayrı security review

Caller yokluğu nedeniyle implementation'dan önce operational-use kararı gerekir. Kullanım retain edilirse host mutation için ayrı read-only security review zorunludur. Review şu soruları cevaplar:

- Manifest path traversal/deletion engelleniyor mu?
- Malformed settings/manifest fail-closed mu?
- Shell command rendering injection-safe mi?
- Home/vault başka bir kullanıcı veya symlink üzerinden dış path'e taşınabiliyor mu?
- Installer ve runtime installer aynı settings.json'da birbirinin entry'sini silebilir mi?
- Upgrade backup ve uninstall modified-file davranışı geri döndürülebilir mi?

# Bölüm B — `remember.py`

## B1. Mevcut capture ve canonical write haritası

`remember.py` mevcut revision'da package implementation değil; 219 satırlık orchestration script'idir.

- `:27-32` memory scope/project identity surface'lerini package'tan alır.
- `:33` `EntityExtractor` package surface'inden gelir; graph rebuild derived projection'dır.
- `:34` `ProjectRegistry` ve `registry_path` package bridge'inden gelir.
- `:35` `capture_safety.evaluate_capture` legacy script surface'inden gelir.
- `:47-61` `memory-validator.py` hyphenated script'ini dynamic load eder; `MemoryValidator` bugün capture validation authority'sidir.
- `:75-90` `is_project_opted_in` ve `proactive_capture_policy` registry'nin fail-closed policy kararını döndürür.
- `:93-120` input normalization, type/content/confidence doğrulaması ve safety evaluation yapar; safety rejection'da registry/persistence çağrısı gerçekleşmez.
- `:122-130` `resolve_capture_scope` ile scope, project label ve opaque project id'yi registry path üzerinden çözer.
- `:132-142` `MemoryValidator.validate_single_and_append` çağrısı yapılır.
- `:144-153` existing fingerprint için duplicate result döner; yeni canonical memory yazılmaz.
- `:155-167` yalnız yeni candidate için `EntityExtractor.build_graph()` derived projection rebuild'i yapılır.

Canonical write scriptin kendisinde değil, `scripts/memory-validator.py:871-886` içindedir:

1. `validate_single_and_append` safety'yi tekrar çağırır (`:874`);
2. mutator `MemoryStore.transact` lock altında latest data'yı reload eder (`:876-885`);
3. duplicate ise `no_change((candidate, issues, is_new))` döner;
4. yeni candidate ise `validated_memory` bucket'ına append eder;
5. `MemoryStore.transact` revision increment, atomic temp/replace ve lock semantiğini uygular.

Caller-level `expected_revision` verilmez; lock altında latest reload lost update'i önler. Bu nedenle capture package'ı `MemoryStore` dosyasına doğrudan yazmamalı, validator'ın transaction surface'ini kopyalamamalı veya ikinci canonical authority oluşturmamalıdır.

## B2. `ProjectRegistry`, scope ve safety invariant'ları

### B2.1 Registry/opt-in

- `ProjectRegistry.proactive_capture_policy` (`scripts/project_registry.py:142-159`) unregistered, archived veya disabled projeyi fail-closed reddeder.
- `remember.py:75-90` bunu yalnız explicit proactive gate API'sinde expose eder; manual `remember()` çağrısı doğrudan opt-in check yapmaz, çünkü manual capture explicit user action'tır.
- Registry mutasyonları `scripts/project_registry.py:117` çevresindeki `file_lock` + atomic write ile yapılır; capture taşıması registry implementasyonunu değiştirmemelidir.
- Project id opaque ve stable kalır; project root path canonical memory content/provenance alanına sızmamalıdır.

### B2.2 Scope

`resolve_capture_scope` (`scripts/memory_scope.py:166-205`) global scope'un project metadata taşımasını, project scope'un project id veya project root gerektirmesini zorunlu kılar. Capture package şu invariant'ları korumalıdır:

- default scope `scope is None` iken project root/current project'tir;
- global explicit capture project/project_id ile reddedilir;
- registry relocation sonrası aynı opaque project id korunur;
- cross-project aynı content farklı fingerprint/identity üretir;
- absolute root path yalnız resolution için kullanılır, persisted project label/id içine yazılmaz.

### B2.3 Capture safety

`capture_safety.py` içindeki `evaluate_capture` (`:96-105`) deterministic secret/transcript/size gate'idir. Remember safety check'i `:118-120`'de validation ve registry resolution'dan önce yapar; validator da `:874`'te ikinci guard olarak `require_safe_capture` çağırır.

Bu iki katman taşımada korunmalıdır. Ancak mevcut `brain_eleven/memory/` altında `capture.py` ve package-owned `capture_safety.py` bulunmuyor. Bu önemli bir migration precondition'ıdır: yeni `brain_eleven/memory/capture.py` package→`scripts.capture_safety` yönünde kalıcı bağımlılık kurmamalı. Implementasyon contract'ı, safety policy için açık package surface (minimal identity-preserving bridge veya safety module'ünün ayrı bounded move'u) seçilmeden onaylanmamalıdır. Safety regex'leri bu Slice 2D planında yeniden tasarlanmayacak ve behavior tuning yapılmayacaktır.

## B3. Remember package contract

Önerilen canonical hedef `brain_eleven/memory/capture.py`'dir. Public API en az şunları kapsar:

- `remember`;
- `default_vault_path`, `default_project_id`;
- `is_project_opted_in`, `proactive_capture_policy`;
- gerekli result/type helper'ları.

Package implementation `MemoryValidator`'ı kopyalamaz. İlk bounded step, validator için explicit stable surface kararını (mevcut legacy module bridge veya daha sonraki ayrı extraction/memory validation package) document eder. `scripts/remember.py` thin adapter olur; `scripts/remember_opt_in.py` package capture policy yüzeyini kullanacak şekilde compatibility update alabilir.

`remember.py` direct CLI parser ve `--check-opt-in`/`--project-root`/`--scope`/`--project-id` behavior'ı korunur. Package API, script-specific `SCRIPT_DIR`/`sys.path` mutation'ına bağımlı kalmaz.

### B3.1 Idempotence ve dedup contract

- Aynı scope + project namespace + type-aware fingerprint ikinci çağrıda `duplicate_returned_existing` döner.
- Duplicate path canonical revision artırmaz, yeni graph rebuild yapmaz ve yeni memory id üretmez.
- Farklı project id aynı içeriği etkileyemez.
- Superseded/inactive record fingerprint adoption davranışı mevcut validator ile aynı kalır.
- Aynı anda iki capture transaction lock altında biri canonical new, diğeri duplicate/no-change olacak şekilde test edilir.
- Safety rejection hiçbir registry/memory/graph effect üretmez.

## 2D sıralama önerisi

### D0 — Installer operational-use + security decision

Önce global installer için C0 kullanım kararı ve manifest/path security review yapılır. Runtime installer ile overlap kesinleşmeden installer implementation'a başlanmaz.

### D1 — Remember capture

`remember.py` gerçek production caller'a sahip, canonical write ve mevcut test contract'ı daha net, scope'u daha dardır. Önce capture package contract'ı ve safety dependency direction onaylanır; sonra implementation ve regression yapılır. D1 bağımsız SHIP olmadan D2 açılmaz.

### D2 — Global installer

Operational-use kararı retain ise `global_install.py` + adapter inversion yapılır. D2 host filesystem security review, runtime installer coexistence matrix'i ve rollback/uninstall kanıtı olmadan kapanmaz. C0 archive/retire ise package migration yerine historical tool sınırı belgelenebilir; production code değişikliği otomatik başlamaz.

## 3. Test ve evidence planı

### 3.1 Installer focused tests

Mevcut `tests/test_phase14_scope.py` installer senaryoları değişmeden geçmelidir. Yeni testler:

- package/adapter/bare-module identity;
- adapter-only AST (script'te install/uninstall mutator, template render veya atomic write kalmaması);
- exact file inventory ve manifest schema;
- idempotent install: settings/file bytes ve backup count;
- conflict preflight: hiçbir partial write olmaması;
- modified managed file uninstall skip;
- manifest path outside `home/.claude` fail-closed;
- malformed manifest/settings fail-closed;
- dry-run byte/tree snapshot unchanged;
- template vault path quoting: spaces, quotes, newline, UNC/drive/WSL;
- install/uninstall coexistence with `brain_eleven.runtime.install` for Claude and Codex paths;
- crash injection between file, settings and manifest writes; recovery/uninstall evidence;
- settings unrelated hooks preserved and exact managed commands only.

### 3.2 Remember focused tests

Mevcut `tests/test_remember.py` ve `tests/test_capture_safety.py` değiştirilmeden geçmelidir. Yeni testler:

- package/adapter/bare-module identity;
- adapter-only AST ve no direct JSON/file write;
- MemoryStore transaction/lock boundary proof;
- duplicate same-project no revision increment/no graph rebuild;
- same content different project isolation;
- registry relocation stable project id;
- unregistered/archived/disabled proactive policy fail-closed;
- explicit manual capture semantics unchanged;
- safety rejection before registry/persistence/graph;
- validator/MemoryStore conflict and concurrent capture replay;
- CLI parity and `remember_opt_in.py` package-surface parity;
- no absolute project root leakage into canonical record.

### 3.3 Full verification gates

Her iki bounded implementation için Slice 2C ile aynı beş kapı uygulanır:

1. **Identity:** package, adapter ve historical bare import aynı public object/function/class/constant identity'sini gösterir.
2. **Adapter-only:** AST/runtime inspection ile duplicate implementation, direct filesystem/canonical write ve reverse package→script ownership kalmadığı doğrulanır.
3. **Parity + safety:** mevcut tests unchanged; idempotence, rollback/uninstall, conflict, path containment, scope, safety and concurrency evidence.
4. **Full verification:** focused suites, `pytest tests -q`, critical flake8 (`E9,F63,F7,F82`), compile/import sanity, `git diff --check`.
5. **Independent review:** installer için ayrı host-filesystem security review; remember için canonical capture/scope review. Implementer `SHIP` veremez.

Her kanıt exact revision, command, exit code ve artifact path ile raporlanmalıdır.

## 4. Tahmini diff büyüklüğü

| Bounded bölüm | Canonical package + adapter | Yeni contract/safety tests | Tahmini toplam |
|---|---:|---:|---:|
| D1 remember/capture | 180–280 satır | 150–250 satır | 330–530 satır |
| D2 global installer | 300–420 satır | 220–360 satır | 520–780 satır |
| Dokümantasyon/evidence | 100–160 satır | — | 100–160 satır |

Tahmin toplamı **950–1.470 satır** aralığındadır. Bu bir LOC hedefi değildir. Validator, ProjectRegistry, capture safety veya runtime installer kopyası oluşturmak kapsam ihlali sayılır.

## 5. Slice 2D çıkış kapısı

Slice 2D review'a ancak şu koşullarda sunulabilir:

- Installer C0 operational-use kararı yazılı;
- runtime installer ile Claude settings overlap matrix'i test edilmiş;
- manifest schema/path containment ve malformed-input fail-closed kanıtı mevcut;
- install/reinstall/uninstall/dry-run ve modified-file preservation kanıtı mevcut;
- remember canonical capture target ve capture-safety package direction kararı yazılı;
- MemoryStore/lock/CAS boundary bypass edilmediği kanıtlı;
- duplicate, project isolation, registry opt-in, safety rejection ve absolute path privacy testleri yeşil;
- mevcut installer/remember/capture safety regression testleri değişmeden geçiyor;
- full suite, critical lint, compile/import ve diff checks yeşil;
- bağımsız review sonuçları yalnız `SHIP`, `FIX-FIRST` veya `RETHINK`.

## 6. Package report şablonu

Her D1/D2 alt paketi ve birleşik Slice 2D raporu şu alanları taşımalıdır:

```text
PACKAGE:
REVISION:
OBJECTIVE:
FILES CHANGED:
CALLER / OPERATIONAL-USE DECISION:
WRITE PATH / AUTHORITY:
SECURITY / SCOPE INVARIANTS:
TESTS ADDED:
TESTS EXECUTED:
SAFETY METRICS:
KNOWN LIMITATIONS:
OPEN FAILURES:
INDEPENDENT REVIEW:
VERDICT: SHIP / FIX-FIRST / RETHINK
```

**Plan status:** REVIEW PENDING — implementation başlamadı, Phase 20 açılmadı.
