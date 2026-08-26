---
tags: [karar, promtgen]
tarih: 2026-08-02
durum: geçerli — gerekçesiz
alan: AI akışı
kanıt: 4beb232
---
# Karar: Tur başına ikinci gizli AI çağrısını kaldır, tek birleşik tura geç

> Idea coach akışında her tur iki AI çağrısı yapıyordu; ikincisi (`discovery-answer-extraction`) ve ona bağlı AI-kural karşılaştırma UI'ı kaldırıldı.

## Bağlam
`Workspace.tsx` artık `IdeaCoachTurn` üzerinden **tek** AI çağrısıyla üretilen anlayış + belirsizlik + soru + kararları tek kartta gösteriyor.

Öncesinde tasarım belgesi yazılmış: `docs/superpowers/specs/2026-08-02-idea-coach-turn-design.md`.

## Gerekçe — YOK
> ⚠️ **Gerekçesiz karar.** 2026-08-20'de soruldu, sahibinin cevabı: *"cevabım yok."*

Bu bir eksiklik değil, bir bulgu. İki ihtimalden biri:
- **Miras:** hiç seçilmedi, öylece oldu (varsayılan, alışkanlık, o an öyle denk geldi).
- **Buharlaşma:** sebep vardı, karar kaldı, sebep gitti.

Hangisi olduğunu bilmeden bu kararı savunamazsın — ve savunamadığın kararı ne koruyabilirsin ne de bilerek bozabilirsin.

**Yapılacak:** bir dahaki sefere bu koda/akışa dokunduğunda, o an neden böyle olduğunu anlarsan buraya bir cümle yaz. Zorlama; kod sana söyleyecek.

## Neyden vazgeçtim
AI ile yerel kuralın yan yana karşılaştırıldığı UI. 12 dosya, +37 / −377.

## Yan bulgu — kapsam sızması
Brief'in listelemediği iki test dosyası da aynı kapsamda temizlenmek zorunda kaldı (`ai-generation-services.test.ts`, `ai-contracts.test.ts`); ikisi de silinen sembollere referans veriyordu ve onlar olmadan `tsc`/test suite yeşile geçmiyordu.

→ Ders: **silinen sembolün test tarafındaki izini brief listelemez, derleyici listeler.**

## Bu kararı ne geri aldırır
Bilinmiyor — gerekçe bilinmeden bu da yazılamaz.

## Kanıt
`4beb232` · 2026-08-02 · 12 dosya, +37 / −377
