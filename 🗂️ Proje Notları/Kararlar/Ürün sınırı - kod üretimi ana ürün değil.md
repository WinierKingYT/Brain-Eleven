---
tags: [karar, promtgen, ürün-sınırı]
tarih: 2026-08-20
durum: geçerli — gerekçesiz
alan: ürün kapsamı
kanıt: docs/product/NON_GOALS.md
---
# Karar: Kod üretimi ana ürün değil

> PromtGen planlama aracıdır. Kaynak kodu doğrudan yazmak/değiştirmek ana ürün akışına **dönüştürülmez**.

## Kapsam dışı sayılanlar
- Canonical planı kullanıcı onayı olmadan değiştirmek
- Her proje alanında uzman veya üretime hazır sonuç iddia etmek
- Kaynak kodu yazmayı/değiştirmeyi ana akışa taşımak
- Planner doğrulanmadan otomatik kod yürütmeyi ana ürün yapmak
- Antivirüs, SAST, hukuki, finansal, klinik doğrulama

## Kontrollü istisna
Yalnız kullanıcı **açıkça isterse**, onaylanmış TaskContract kapsamı içinde ve **Labs** üzerinden ikincil araç olarak.

## Gerekçe — YOK
> ⚠️ **Gerekçesiz karar.** 2026-08-20'de soruldu, sahibinin cevabı: *"cevabım yok."*

Bu bir eksiklik değil, bir bulgu. İki ihtimalden biri:
- **Miras:** hiç seçilmedi, öylece oldu (varsayılan, alışkanlık, o an öyle denk geldi).
- **Buharlaşma:** sebep vardı, karar kaldı, sebep gitti.

Hangisi olduğunu bilmeden bu kararı savunamazsın — ve savunamadığın kararı ne koruyabilirsin ne de bilerek bozabilirsin.

**Yapılacak:** bir dahaki sefere bu koda/akışa dokunduğunda, o an neden böyle olduğunu anlarsan buraya bir cümle yaz. Zorlama; kod sana söyleyecek.

## Bu kararı ne geri aldırır
Bilinmiyor — gerekçe bilinmeden bu da yazılamaz.

## Kanıt
`docs/product/NON_GOALS.md`
