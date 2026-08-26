---
tags: [karar, promtgen, ürün-sınırı]
tarih: 2026-08-20
durum: geçerli — ama gerekçesi bayat
alan: mimari
kanıt: docs/product/NON_GOALS.md + README + sahibinin beyanı 2026-08-20
---
# Karar: Local-first; bulut senkronizasyonu, hesap ve çok kullanıcılı işbirliği yok

## Ne yerine ne
| İhtiyaç | Bulut çözümü (reddedildi) | Seçilen |
|---|---|---|
| Depolama (web) | sunucu DB | IndexedDB |
| Depolama (masaüstü) | sunucu DB | WAL modlu SQLite |
| Dayanıklılık | sunucu yedeği | 20 otomatik yedekleme + kurtarma |
| Taşıma | hesap senkronu | SHA-256 doğrulamalı `.promtgen` paketi |

## Gerekçe — ve gerekçenin son kullanma tarihi
**Orijinal gerekçe:** proje bir gün **yayınlanabilir** diye düşünülmüştü. Yayınlanacak bir araçta local-first ucuzun ötesinde doğru seçim: sunucu maliyeti yok, hesap yok, veri kullanıcının kendi makinesinde kalır.

**Sonra hedef değişti:** "bana özel olsun" denildi. Proje kişisel kullanıma döndü.

> ⚠️ **Gerekçe öldü, karar yaşıyor.** Bugün local-first'ü ayakta tutan şey artık onu doğuran sebep değil. Mimari muhtemelen hâlâ doğru (kişisel araçta local-first daha da basit) — ama **artık farklı bir sebeple doğru**, ve bu sebep hiçbir yerde yazılı değil.

## Dokümanla gerçek arasındaki boşluk
`NON_GOALS.md` bunu kesin bir ürün ilkesi gibi yazıyor: *"Bulut senkronizasyonu, hesap veya çok kullanıcılı işbirliği sunmak"* kapsam dışı.

Gerçekte bu bir ilke değil, **hedef değişikliğinin kalıntısı.** Fark önemli: yarın yayınlamak istersen kendi NON_GOALS'ünü aşılmaz bir yasa sanıp kendi kararını kendine engel yaparsın. Değil — geri alınabilir, sadece kimse geri alma koşulunu yazmamış.

## Bu kararı ne geri aldırır
Projeyi gerçekten yayınlama kararı **ve** kullanıcıların cihaz arası senkron istemesi. İkisi birden olmadan bulut gerekmiyor.

→ Açık soru: [[Açık Döngüler]] — PromtGen yayınlanacak mı?

## Kanıt
`docs/product/NON_GOALS.md` · `README.md` · sahibinin beyanı (2026-08-20): *"sadece local oldu... belki ilerde yayınlarım diye, ama sonra bana özel olsun diye düşündüm"*
