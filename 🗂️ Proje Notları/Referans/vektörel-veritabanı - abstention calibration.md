---
type: observation
title: Abstention Calibration - Confidence-Gated Retrieval
status: active
created: 2026-09-23
tags: [retrieval, rag, abstention, calibration, reference, not-yet-applied]
source: local project — C:\Users\faruk\Documents\ChatGPT\vektörel database (Ahmet'in kendi kişisel projesi, GitHub değil)
---

# Abstention Calibration

**Bu bir Brain-Eleven kararı değil.** Ahmet'in kendi "Kişisel Vektörel Veritabanı"
(Qdrant tabanlı, kişisel dokümanlar için RAG) projesinden gözlemlenmiş bir teknik —
o projede uygulanmış ve orada gerçekten çalışıyor, ama Brain-Eleven'in kendi
verisi/eşikleriyle hiç test edilmedi. Buraya, `retrieval_decision_v2`'nin
gelecekteki bir yeniden tasarımı düşünüldüğünde referans olarak bakılsın diye
yazıldı.

## Neden buraya yazıldı

`docs/history/weakness/WEAKNESS-IG01F-V2-REGRESSION-INVESTIGATION-EVIDENCE-REPORT.md`
(2026-09-23), `retrieval_decision_v2/engine.py`'nin sözcük-örtüşmesi tabanlı alaka
filtresinin **iki yönde de** güvenilmez olduğunu buldu: aynı bileşen hem gürültüyü
aşırı-dahil ediyor (bu oturumda daha önce düzeltilen bir hata, `d965015`) hem de
kısa-ama-doğru cevapları aşırı-hariç ediyor (bugün bulunan yeni bulgu). Sonuç:
"yapısal bir kısıtlama, dar bir hata değil" — gerçek bir düzeltme, filtrenin
sözcük-örtüşmesi yaklaşımının kendisini değiştirmeyi gerektirir.

## Teknik (vdb projesinden, doğrudan alıntı değil, gözlemlenen yaklaşım)

- Sabit bir eşik yerine, **kalibre edilmiş** bir eşik kullanılıyor:
  `abstention-calibrate` komutu, bilinen pozitif/negatif (relevant/irrelevant)
  bir validation split'i üzerinde, "pozitif kabul ile negatif abstention'ı en iyi
  ayıran" eşiği veriden türetiyor — elle seçilmiş sabit bir sayı değil.
  Girdi: sorgu başına en yüksek cosine skoru + gerçek relevant/irrelevant etiketi.
  Çıktı: o split için optimal eşik.
- Eşiğin altında kalan sonuçlar için sistem **"bulamadım" diyor**, yanlış ya da
  düşük-güvenli bir sonucu zorla döndürmüyor. HTTP `/v1/search` yanıtı bunu
  `abstention_reason` (`no_candidates` vs `below_min_score`) ile ayırt ediyor —
  "hiç aday yok" ile "adaylar var ama güvenmiyorum" farklı, izlenebilir durumlar.
- Kalibrasyon girdisi bilinçli olarak "önceden eşik uygulanmamış, rerank kapalı,
  tek tekrarlı" ham dense skorlardan üretiliyor — böylece kalibrasyon, zaten
  filtrelenmiş bir sinyali kendi kendine doğrulamıyor.

## Brain-Eleven'e nasıl uygulanabilir (spekülatif, test edilmedi)

`retrieval_decision_v2`'nin şu anki sözcük-örtüşmesi filtresi yerine (ya da onunla
birlikte): gerçek kabul/red kararlarından (review kuyruğundaki insan kararları,
ya da IG01-F/IG01E gibi mevcut etiketli test setleri) bir kalibrasyon eğrisi
türetmek, ve düşük-güvenli adaylarda seçim yapmak yerine açıkça "yetersiz kanıt"
sinyali vermek — bugünün IG01-F bulgusundaki "SQLite kararı" vakasında olduğu gibi
adayı tamamen atmak yerine.

**Önemli sınırlama:** Bu, Brain-Eleven'in kendi corpus'unda hiç ölçülmedi. Vaat
edici bir yön, doğrulanmış bir çözüm değil — herhangi bir uygulama, kendi
eşiğini kendi verisiyle (D0/D1/IG01E gibi) yeniden kalibre etmeyi gerektirir.

## Bağlantılar

[[WEAKNESS-IG01F-V2-REGRESSION-INVESTIGATION-EVIDENCE-REPORT|IG01-F V2 Regression Investigation]]
(not: bu dosya vault dışında, `docs/history/weakness/` altında — Obsidian bu linki
çözemeyebilir; tam yol: `docs/history/weakness/WEAKNESS-IG01F-V2-REGRESSION-INVESTIGATION-EVIDENCE-REPORT.md`)
