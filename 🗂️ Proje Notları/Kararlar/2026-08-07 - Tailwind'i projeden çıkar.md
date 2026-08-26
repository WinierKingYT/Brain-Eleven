---
tags: [karar, promtgen]
tarih: 2026-08-07
durum: geçerli
alan: frontend / build
kanıt: 3f4ce5c
---
# Karar: Tailwind'i projeden çıkar, tabanı elle yaz

> PromtGen'den Tailwind bağımlılığı kaldırıldı; yerine Preflight'in hesaplanmış sonucunu birebir üreten elle yazılmış bir taban sıfırlama kondu.

## Bağlam
Spec ve plan, Tailwind'in tek kullanıcısının `LiveAnnouncer`'daki `sr-only` div olduğunu söylüyordu. Yani "neredeyse hiç kullanılmıyor, çıkar gitsin" görünüyordu.

## Gerekçe
**Ölçüm spec'i çürüttü.** `@import "tailwindcss"` yalnızca yardımcı sınıf üretmiyordu, **Preflight**'i de getiriyordu ve uygulamanın o günkü görünümü ona dayanıyordu. Tailwind çıkarılınca görsel sözleşme testi **1285 farkla** düştü:

| Ne bozuldu | Adet |
|---|---|
| line-height (Preflight'in 1.5 mirası) | 1170 |
| font-weight | 41 |
| padding/margin | 27 |
| font-size | 21 |
| font-family (form denetimleri Arial'a düştü) | 14 |
| border-color | 6 |

Karar yine de çıkarma yönünde verildi — ama taban sıfırlama elle yazılarak.

## Neyden vazgeçtim
- Tailwind'in yardımcı sınıf ergonomisi.
- Karşılığında: 618 satır silindi, 113 satır yazıldı; bağımlılık gitti, kaskad kontrolü bize geçti.
- Ardından 5 günlük CSS göçü (08-07 → 08-12, "pg diline çevir" serisi) ve bir regresyon: `fix(css): Tailwind kaldirilinca bicimsiz kalan koken rozetini onar`.

## Teknik detay — neden `@layer base`
Kasıtlı seçim: Tailwind de Preflight'i bu katmanda yayınlıyordu. Böylece dosyanın katmansız geri kalanı **özgüllüğüne bakılmaksızın** üstte kalır — kaskad düzeni değişmedi.

## Bu kararı ne geri aldırır
*(sen doldur — hangi koşulda Tailwind'e dönerdin?)*

## Kanıt
`3f4ce5c` · 2026-08-07 · 7 dosya, +113 / −618
