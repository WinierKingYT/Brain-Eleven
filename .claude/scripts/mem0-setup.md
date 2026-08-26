# mem0 Setup for Brain-Eleven

Jane'nin semantic memory'si — otomatik hafıza genişletme.

## Kurulum Adımları

### 1. Interactive Session'da mem0-mcp'i Authorize Et

```bash
claude -p "/mcp"
# Atau: /mcp komutunu çalıştır
```

mem0-mcp seçeneklerinden:
- "Authenticate with mem0"
- OAuth flow'u tamamla

### 2. mem0 Scope'u Belirle

Brain-Eleven için scope: `brain-eleven-core`

```bash
claude -p "mem0 scope set brain-eleven-core"
```

### 3. Jane'nin Core Memory'sini Seeding Et

Jane - Core.md içeriğini mem0'a ekle:

```bash
claude -p "
Add to mem0:

Name: Jane (Brain-Eleven Companion)
Type: assistant_profile
Scope: brain-eleven-core

Owner: Eleven
Role: Hafıza + İçerik Yönetimi + Bağlantı Kurma

Work Areas: Web tasarım, oyun geliştirme, uygulama geliştirme, mobil, oyun tasarımı

Protocol:
- Morning: Read Last Session, open Threads
- Evening: Write Daily summary
- Weekly (optional): Weekly summary

Rules:
- Never delete notes
- Wikilinks use filename: [[dosyaadi]]
- Dates: YYYY-MM-DD
"
```

### 4. Hook'ları mem0'a Bağla

SessionEnd hook'unda:

```bash
# Daily'yi mem0'a gönder
claude -p "Summarize today's Daily and add to memory"
```

### 5. Query Test Et

```bash
claude -p "mem0 search brain-eleven-core 'web tasarım'"
```

---

## Scope Yönetimi

| Scope | Kullanım | Boyut |
|---|---|---|
| `brain-eleven-core` | Jane profil + Karar/Ders/Proje | 1-2k token |
| `brain-eleven-daily` | Daily yazıları | 500 token |
| `brain-eleven-threads` | Aktif konular | 300 token |

---

## Otomatizasyon

Hook'lar active olduğunda:
- SessionEnd → Daily özet → mem0
- PreCompact → Weekly → mem0
- UserPromptSubmit (her 15) → Kontrol → mem0

---

**Status**: Hazırlanıyor (auth bekleniyor)
