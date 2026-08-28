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

---

**v3 thesis**: Memory must be a mechanism, not a discipline. Hooks automate extraction; Claude retrieves context automatically on session start.

**Hooks Status**: ✅ ACTIVE (SessionStart loads context, SessionEnd extracts to JSON, prompt-counter creates checkpoints)
