# AGENTS.md — Brain-Eleven kuralları (Codex ve diğer ajanlar)

Bu dosya bu depoda çalışan AI ajanları içindir. Proje otoritesi `CLAUDE.md`,
`PROJECT-STATUS.md` ve `DOCUMENTATION-AUTHORITY.md`'dedir; burası onların
kısa, uygulanabilir özetidir. Çelişki olursa o belgeler geçerlidir.

## İlk soru

Yeni bir iş, paket veya sözleşme açmadan önce cevapla:

> **Bu, hatırlama testini ölçülebilir şekilde ilerletiyor mu, ya da bunu
> doğrudan yapan bir şeyin önünü açıyor mu?**

Cevap hayırsa işi açma (`docs/programs/WORK-INTAKE-RULE.md`). Güvenlik,
gizlilik ve veri kaybı hataları bu sorudan muaftır; her zaman düzeltilir.

## Değiştirilmeyenler

- Eşik, holdout, corpus, Phase 20 ve V2 modu değişmez.
- Test atlanmaz, karantinaya alınmaz, gevşetilmez; başarısız test silinmez.
- Canonical otorite `MemoryStore`, `StateStore`, `ProjectRegistry`'dir;
  ikinci bir hafıza/durum sistemi kurulmaz. Hafıza yazımı yalnız
  `scripts/memory_store.py` / `MemoryStore` üzerinden.
- mem0'a yazılmaz.

## Çalışma biçimi

- İşe başlamadan: `CONTRIBUTING.md`'nin "Check GitHub before assuming you
  know the whole picture" komutlarını çalıştır; çalışma ağacındaki
  ilgisiz değişiklikleri koru.
- Mevcut sahibi bul ve onu genişlet. Varsayılan: yeni bağımlılık yok, yeni
  soyutlama yok, dış sözleşme değişikliği yok; istisnayı gerekçelendir.
- Hata düzeltirken: yeniden üret → kök neden → düzelt → aynı kontrolle
  doğrula.
- Master'a doğrudan push yok. Her iş kendi dalında, PR ile. Force push yok.
- Rapora, PR'a ve commit'e konuşma metni, sır, token veya tam dosya yolu
  yazılmaz.
- Yeni runtime testleri `.github/workflows/runtime.yml` test listesine
  eklenir. Bilinen 12 `w06c0`/`w06c0r1` hatası ve `quality` işi dışında
  yeni kırmızı kabul edilmez.

## Kanıt

Hatırlamayı etkileyen her değişiklikte önce/sonra ölçümü ver:

```
python -m brain_eleven recall-probe                      # resmî 5 soru
python -m brain_eleven recall-probe --questions <yerel>  # ek sorular (repo'ya girmez)
```

Ölçüm, değişikliğin etkisini gerçekten ölçebilmeli: sağlayıcı yoksa veya
teslim kapalıysa "etki ölçülmedi" de, 0→0'ı sonuç sayma. Testlerin geçmesi
davranışın doğru olduğunun kanıtı değildir.

## PR kapanışı

Her PR açıklamasının sonunda:

```
Kabul ölçütü: <ölçülebilir; tercihen recall-probe>
Önce/sonra:   <tablo veya sayı>
Kanıtlanmayan: <çalıştırılamayan kontrol, mock sınırı, varsayım>
Karar:        SHIP / FIX-FIRST / BLOCKED / UNKNOWN
```

Aynı ajanın kendi incelemesi "bağımsız inceleme" diye sunulmaz.
