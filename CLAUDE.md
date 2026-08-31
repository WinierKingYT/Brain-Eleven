# Brain-Eleven: Eleven'in ikinci beyni

Obsidian + Claude Code, hafızası kendisi yazan sistem. v2 başlangıç.

## Yükleme sırası

1. Vault iskeletı ✓
2. CLAUDE.md (bu dosya) ✓
3. Hooks ✓ (SessionStart, SessionEnd, prompt-counter, audit)
4. Companion hafıza (🔮 850-Companion/) ✓
5. İçerik iskeletı (🧠 Brain-Eleven ana sayfa) ✓
6. Git (opsiyonel) ✓

## Göreve göre yönlendirme

| Kullanıcı ister | Yapılacak | Kısayol |
|---|---|---|
| Günlük not | 🔮 850-Companion/Daily'ye gir, {{DATE}} başlığında yaz | `/daily` |
| Proje notu | 🗂️ Proje Notları/'na yaz, başlıkta proje adı | `/project` |
| Kaynağı kaydet | 📚 Kaynaklar/'na wikilink + özet | `/source` |
| Geçmiş görüntüle | 🔮 850-Companion/Last Session veya Threads | `/history` |

## Hafıza protokolü

- **Günlük girdiler**: 🔮 850-Companion/Daily/{{DATE}}.md
- **Aktif konular**: 🔮 850-Companion/Threads (bölüm başlıkları)
- **Kapatılan**: 🔮 850-Companion/Threads ## Closed Threads
- **Profil**: 🔮 850-Companion/Jane: Core (bu dosya)
- **Kural'lar**: 🔮 850-Companion/Rules

## Devir kuralı

1. Oturum başında: Last Session oku, Threads'i açık tut
2. Oturum sonunda: {{DATE}} daily'yi yazışır'dan önce kaydet
3. Gece derleyicisi: Günlükleri makine-okunur bilgiye çevir → 📚 Kaynaklar/

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

**Hooks Status**: ✅ ACTIVE (SessionStart loads context, SessionEnd extracts to JSON, prompt-counter creates checkpoints)
