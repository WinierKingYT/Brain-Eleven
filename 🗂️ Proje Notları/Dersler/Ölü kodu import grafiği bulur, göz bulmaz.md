---
tags: [ders, refactor]
tarih: 2026-08-08
kayıp-süre: —
alan: bakım
---
# Ders: Ölü kodu import grafiği bulur, göz bulmaz

## Belirti
`src` altındaki **258 dosyanın 40'ına hiçbir yerden erişilmiyordu.** 6803 satır ölü kod. Gözle bakınca hepsi normal görünen dosyalardı.

## Kök neden
Ölü kod tek seferde ölmez, **kuşaklar halinde** birikir. Bu projede üç kuşak çıktı:
1. React öncesi vanilla yığın (16 dosya) — `main.js`, `presentation/`, `state/`, `ai/` sağlayıcıları, `prompts/`, `exporters/`, `storage/`, `planning/`, `security/`
2. Arayüzden düşürülmüş React panelleri (23 dosya)
3. Kalanlar

Her göç bir kuşak bırakıyor ve kimse arkasına dönüp bakmıyor.

## Çözüm
Import grafiği **giriş noktasından** yürütüldü: `src/react/main.tsx` + bütün testler, betikler, benchmark'lar ve deneyler. Grafikte olmayan = ölü.

Not: `runtime-boundary.test.js` bunların bir kısmını üretim grafiğinde zaten **yasaklıyordu** — yani sinyal vardı, kimse toplamamıştı.

## Erken uyarı işareti
> **Büyük bir göç yaptıysan (vanilla → React, kütüphane değişimi, panel kaldırma), göçten sonra import grafiğini yürüt.** Ölü kuşak tam orada birikir.

Ve: elinde zaten sinyal veren bir test varsa (`runtime-boundary` gibi), onu uyarı değil **envanter** olarak kullan.

## Kaynak
`cfcb837` · 2026-08-08 · 42 dosya, +1 / −6813. Doğrulandı — commit gövdesinde kuşak dökümü yazılı.
