---
name: beyin
description: Brain-Eleven ikinci beyni. Kullanıcı "hatırla", "bunu kaydet", "ne biliyoruz", "geçen sefer ne yaptık", "son işler", "onay bekleyenler" dediğinde ya da bir projenin geçmiş kararlarını/derslerini bulman gerektiğinde kullan.
---

# Beyin

Brain-Eleven oturumları kendiliğinden yakalar ve ilgili hafızayı bağlama ekler.
Bu skill, kullanıcı açıkça bir şey istediğinde ne çalıştıracağını söyler.
Bütün komutlar şu önekle çalışır:

```text
{{PYTHON}} -m brain_eleven --vault "{{VAULT_PATH}}" <komut>
```

## Ne zaman ne

| Kullanıcı | Komut |
|---|---|
| "Bunu hatırla / kaydet" (tek bir karar, ders, gözlem) | aşağıdaki **Kaydet** bölümü |
| "X hakkında ne biliyoruz?" | `context "<soru>" --project-root "$PWD"` |
| "Son günlerde ne yaptık?" | `recap --days 7` (ya da `--since YYYY-AA-GG --until YYYY-AA-GG`, `--project <ad>`) |
| "Onay bekleyenler / hafıza kuyruğu" | `digest`; tek tek onay için `review` (tarayıcı açar) |
| "Şu kayıt yanlış, sil" | `retire <mem_id> --note "<neden>"` (silmez, iptal eder) |
| "Bu projeyi incele, kararlarını çıkar" | `/study` komutu |
| "Daha az / hiç bağlam ekleme" | `profile economical` ya da `profile manual`; geri: `profile normal` |
| "Hafızayı göster" | `🔮 Companion/Hafıza/<proje>.md` notunu oku (güncel değilse önce `notes`) |
| "Nerede kalmıştık?" | `🔮 Companion/Oturumlar/<proje>.md` notunu oku |

## Kaydet

Yalnız açık bir karar, ders, gözlem ya da açık iş kaydedilir; sohbetin tamamı
ya da tahmin kaydedilmez. Metin tek başına anlaşılır olsun ve NEDEN'i içersin.

```text
{{PYTHON}} "{{VAULT_PATH}}/scripts/remember.py" --vault "{{VAULT_PATH}}" --project-root "$PWD" --type <decision|lesson|observation|open_loop> --content "<metin>"
```

## Seni tanıma notları

`🔮 Companion/Core.md` (sahip kim, nasıl çalışmak istiyor) ve
`🔮 Companion/Kurallar.md` (sahibin düzeltmeleri) her oturum başında bağlama girer.

- Sahip seni düzeltirse ("hayır, böyle değil", "bundan sonra şöyle yap") aynı
  oturumda `Kurallar.md`'ye bir madde ekle: `- **kural:** … **neden:** …`
  (tek satır). Tek seferlik istek kural değildir.
- Sahip kendisi hakkında kalıcı bir şey söylerse (ad, hitap, çalışma biçimi)
  `Core.md`'deki ilgili maddeyi güncelle; tahmin yazma.
- İkisini de kısa tut; uzun anlatım ayrı nota gider.

## Kurallar

- Sır, token, parola, kart/hesap numarası, tam dosya yolu ya da sohbet dökümü
  asla kaydedilmez.
- Hafıza notları türetilmiştir; nota elle yazmak hafızayı değiştirmez.
- Bir şey çalışmıyorsa `beyin-doktor` skill'ine geç.
