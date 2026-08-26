---
tags: [ders, frontend, css]
tarih: 2026-08-07
kayıp-süre: ~5 gün (CSS göçü) + 1 regresyon
alan: frontend / build
---
# Ders: CSS framework'ü importu sadece yardımcı sınıf getirmez, taban sıfırlama da getirir

## Belirti
Tailwind projeden çıkarıldığında görsel sözleşme testi **1285 farkla** düştü — hiçbiri yardımcı sınıf kaybı değildi:

```
1170  line-height   (Preflight'in 1.5 mirası kayboldu)
  41  font-weight
  27  padding/margin
  21  font-size
  14  font-family   (form denetimleri Arial'a düştü)
   6  border-color
```

## Ne sandım
**Spec ve plan yanlış söylüyordu:** Tailwind'in tek kullanıcısı `LiveAnnouncer`'daki `sr-only` div. Yani "kullanılmıyor, çıkar gitsin".

Bu, dersin en önemli kısmı — plan makul, okunaklı ve **yanlıştı**.

## Kök neden
`@import "tailwindcss"` iki iş yapıyor: yardımcı sınıf üretmek **ve Preflight'i (taban sıfırlama) yayınlamak.** Uygulamanın görünümü ikincisine dayanıyordu ve bunu hiçbir yerde kimse yazmamıştı — çünkü kimse yazmaz, framework sessizce verir.

## Çözüm
Preflight'in **hesaplanmış sonucunu birebir üreten** taban sıfırlama elle yazıldı. `@layer base` kasıtlı seçildi: Tailwind de Preflight'i bu katmanda yayınlıyordu, böylece dosyanın katmansız geri kalanı özgüllüğüne bakılmaksızın üstte kalır — kaskad düzeni değişmedi.

## Erken uyarı işareti
> **Bir bağımlılığı "neredeyse kullanılmıyor" diye çıkarmadan önce, kullanımı sınıf/sembol arayarak değil ÖLÇEREK doğrula.**

Grep "kim import ediyor"u bulur; **yan etkiyi bulmaz**. Yan etkisi olan her paket (CSS reset, polyfill, global patch, side-effect import) bu tuzağı kurar. Görsel sözleşme testi olmasaydı bu 1285 fark sessizce üretime giderdi.

Genel kural: **plan bir hipotezdir, ölçüm hakemdir.** Bu projede ölçüm planı çürüttü ve haklı çıktı.

## Kaynak
`3f4ce5c` · 2026-08-07 · intelligent-oppenheimer. Doğrulandı — commit gövdesinde ölçüm sayıları yazılı.
