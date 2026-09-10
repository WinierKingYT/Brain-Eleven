# Brain-Eleven: Eleven'in ikinci beyni

Obsidian + Claude Code, hafızası kendisi yazan sistem. v2 başlangıç.

## Güncel program ve belge otoritesi

**PHASE 20: FROZEN. ACTIVE PROGRAM: INTELLIGENCE GRADUATION (IG).**
Önce PROJECT-STATUS.md, INTELLIGENCE-GRADUATION.md, IG00-FREEZE-BASELINE.md ve
DOCUMENTATION-AUTHORITY.md oku. IG-00 bağımsız kabul edilmeden IG-01 açılmaz.
Eski faz planları tarihsel/gelecek tasarımdır; Knowledge Engine başlatılmaz.
Feature freeze, teknik kapanış veya intelligence graduation demek değildir.
Canonical authority MemoryStore, StateStore ve ProjectRegistry'de kalır.
Model yalnız öneri üretir; safety ve intelligence ayrı ölçülür.

Aşağıdaki eski vault kurulum/not kullanım rehberi runtime otoritesi değildir.
Güncel üretim yolları ve kurulu istemci ayrımı RUNTIME-DATAFLOW.md içindedir.

## Yükleme sırası (tarihsel rehber)

1. Vault iskeletı ✓
2. CLAUDE.md (bu dosya) ✓
3. Hooks ✓ (SessionStart, bounded capture hand-off, audit)
4. Companion hafıza (🔮 Companion/) ✓
5. İçerik iskeletı (🧠 Brain-Eleven ana sayfa) ✓
6. Git (opsiyonel) ✓

## Göreve göre yönlendirme

| Kullanıcı ister | Yapılacak | Kısayol |
|---|---|---|
| Günlük not | 🔮 Companion/Daily.md içine {{DATE}} başlığında yaz | `/daily` |
| Proje notu | 🗂️ Proje Notları/'na yaz, başlıkta proje adı | `/project` |
| Geçmiş görüntüle | 🔮 Companion/Last Session.md veya Threads.md | `/history` |

## Hafıza protokolü

- **Günlük girdiler**: 🔮 Companion/Daily.md (tek dosya, tarih başlıklarıyla)
- **Aktif konular**: 🔮 Companion/Threads.md (bölüm başlıkları)
- **Kapatılan**: 🔮 Companion/Threads.md ## Closed Threads
- **Profil**: 🔮 Companion/Jane - Core.md
- **Açık döngüler**: 🔮 Companion/Açık Döngüler.md

Not: Kaynak kaydetme (`📚 Kaynaklar/`) ve ayrı bir kurallar dosyası
(`Rules`) tasarımda geçiyordu ama henüz oluşturulmadı — CLAUDE.md'nin bu
sürümü yalnızca var olan dosyalara işaret eder. Biri gerekli görürse önce
burada bir satırla kayda geçirilip sonra klasör/dosya açılmalı; tersi
sırayla (önce dosya, sonra iz sürülemeyen referans) bu proje daha önce
defalarca doküman sürüklenmesine yol açtı.

## Devir kuralı

1. Oturum başında: Last Session.md oku, Threads.md'yi açık tut
2. Oturum sonunda: {{DATE}} daily girdisini yazışmadan önce kaydet

## Doğrulama

- Hiçbir not silinmez (Recycle Bin kontrol et)
- Wikilink'ler bozuk mu? → `claude -p "lint --vault ."` (opsiyonel)
- Git tracking opsiyonel (bak: PHASE 9)

## Çapraz proje hafıza yakalama

- Açıkça istenen tekil kayıt: global `/remember` komutu → `scripts/remember.py`
- Memory scope açıkça `global` veya `project` olur. Dedup kimliği `scope + project_id + type + normalize edilmiş içerik` bileşimidir; global memory için `project_id` boştur.
- Capture sırasında `project_id`, vault-local `.claude/project-registry.json` içindeki opaque kimlikten çözülür. Registry yoksa yalnızca uyumluluk fallback'i olan kök hash'i kullanılır; tam dosya yolu canonical memory'ye yazılmaz.
- Varsayılan retrieval, proje verilmezse yalnızca global memory'leri; proje verilirse global + o projeyi getirir. Diğer projeler yalnızca açık `retrieval_scope=all` isteğiyle dahil edilir.
- Proaktif yakalama varsayılan olarak kapalıdır. İzin verilen proje kökleri `.claude/remember-config.json` içindeki `proactive_opt_in_projects` listesine mutlak yol olarak eklenmelidir.
- Opt-in kontrolü bozuk veya eksik yapılandırmada fail-closed çalışır; sır, token, parola ve tam oturum dökümü kaydedilmez.
- Eski store'lar için bir defalık, idempotent geçiş: `python scripts/migrate-memory-scope.py --vault .` (önce `.bak` üretir).
- Canonical memory yazımları `scripts/memory_store.py` üzerinden revision + lock + atomic write ile yapılır; API güncellemeleri `expected_revision` ile CAS kullanabilir.
- Global kurulum/geri alma: `python scripts/install-cross-project-memory.py --dry-run`, ardından `--home <home> --vault <vault>`; mevcut ayarlar ve kullanıcı tarafından değiştirilmiş dosyalar korunur.

---

**v3 thesis**: Memory must be a mechanism, not a discipline. Hooks automate extraction; Claude retrieves context automatically on session start.

**Hooks Status (2026-09-07)**: Native Claude/Codex V2 remains **SHADOW**. The preserved PRE-13 checkpoint does not emit V1 through native SHADOW; a separately installed global Claude V1 hook exists. IG-00 reconciles single V1 SessionStart ownership before acceptance. See RUNTIME-DATAFLOW.md for the verified boundary; configured hooks do not prove native trust or actual delivery. Windows hooks and verification helpers must run hidden. Do not open Python consoles or browser panels during background work. docs/history/PRE13-TECHNICAL-CLOSURE.md preserves prior evidence and limitations; Phase 20 is now feature-frozen under IG, not graduated.
