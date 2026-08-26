---
tags: [karar, promtsitesi, deploy]
tarih: 2026-07-23
durum: geçerli — koşullu
alan: veritabanı / deploy
kanıt: cab32d7
---
# Karar: Deploy imajında Prisma session-level advisory lock'u kapat

```dockerfile
ENV PRISMA_SCHEMA_DISABLE_ADVISORY_LOCK=1
```

## Bağlam
Deploy sırasında migration takılıyordu: **pooled Neon bağlantıları migration lock'unu elinde tutuyordu.** Prisma migration'ı session-level advisory lock alıyor; connection pooling'de o session havuzda kalınca lock da kalıyor.

## Gerekçe
Kodda yazılı: *"Render serializes deploys for this service. Disabling Prisma's session-level advisory lock avoids pooled Neon connections retaining the migration lock."*

Yani lock gereksiz **çünkü platform zaten aynı garantiyi veriyor**: Render bu servis için deploy'ları sıraya sokuyor. Lock'un koruduğu şey (eşzamanlı migration) platform seviyesinde zaten imkânsız.

## ⚠️ Bu kararı ne geri aldırır — YAZILI DEĞİLDİ
Bu kararın güvenliği **tek bir varsayıma** dayanıyor: *Render deploy'ları sıraya sokar.*

Varsayım düşerse migration koruması olmadan eşzamanlı migration riski doğar. Düşme yolları:
- Render'dan başka bir platforma taşınmak
- Aynı servisi ölçeklendirip paralel deploy açmak
- Render'ın bu davranışı değiştirmesi
- Migration'ı CI'dan veya elle çalıştırmak (Render'ın sıralaması devrede değil)

→ **Taşınma anında bu satır kontrol edilmeli.** Dockerfile'daki bir `ENV` satırı taşınırken kimsenin bakmadığı yerdir; yorum "neden"i söylüyor ama "ne zaman geçersizleşir"i söylemiyor.

## Kanıt
`cab32d7` · 2026-07-23 · Dockerfile +3
