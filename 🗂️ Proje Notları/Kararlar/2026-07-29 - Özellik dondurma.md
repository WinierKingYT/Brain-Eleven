---
tags: [karar, promtgen]
tarih: 2026-07-29
durum: etkin
alan: ürün / süreç
kanıt: docs/product/FEATURE_FREEZE.md
---
# Karar: Alpha öncesi özellik dondurma

> Yeni özellik geliştirme durduruldu; dönemin kapsamı "mimari birleştirme ve kanıt".

## Gerekçe
**Başarı yeni özellik sayısıyla değil, mevcut üretim akışının tek sahipli, testli, geri alınabilir ve anlaşılır olmasıyla ölçülür.**

Bu cümle bu projedeki en çok tekrar eden değer. Commit geçmişinde karşılığı görülüyor: "tek kaynak", "tek sahip", "tekilleştir", "birleştir" kalıbı 08-02 → 08-15 arasında sürekli geçiyor.

## Dondurulanlar
Yeni AI sağlayıcı ve ajan rolleri · yeni domain paketleri · yeni export formatları · yeni ana navigasyon/dashboard · otomatik kod yürütmenin ana ürüne taşınması · marketplace, cloud sync, çok kullanıcılı · mobile, AI/RAG, oyun, 3D, multiplayer alan genişlemesi.

## İzin verilenler
Veri kaybı/güvenlik/yanlış canonical üreten hata düzeltmeleri · mimari birleştirme · migration, recovery, typed command, typed IPC, invariant güçlendirme · Golden Path'i sadeleştiren UX · test keşfi, CI kanıtı, benchmark dürüstlüğü, gerçek kullanıcı araştırması.

## Bu kararı ne geri aldırır
Dondurmanın **istisna kapısı** var ve iki kez kullanılmış:
- 2026-08-06 — fikir genişletme panosu (`docs/product/freeze-exceptions/`)
- 2026-08-16 — ürün modeli V3 şartnamesi, dondurma istisnası 2

→ Dondurma yasak değil, **sürtünme**. Bu iyi tasarım: kararı geri almayı imkânsız değil pahalı yapıyor.

## Kanıt
`docs/product/FEATURE_FREEZE.md` · başlangıç 2026-07-29 · durum: Etkin
