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
| "Onay bekleyenler / hafıza kuyruğu" | aşağıdaki **Onay** bölümü |
| "Bunu neden hatırlıyorsun?" / "bu nereden geldi?" | `why <mem_id>` (kaynak rolü, onay, varsa asıl mesaj) |
| "Şu kayıt yanlış, sil" | `retire <mem_id> --note "<neden>"` (silmez, iptal eder) |
| "Bu projeyi incele, kararlarını çıkar" | `/study` komutu |
| "Daha az / hiç bağlam ekleme" | `profile economical` ya da `profile manual`; geri: `profile normal` |
| "Hafızayı göster" | `🔮 Companion/Hafıza/<proje>.md` notunu oku (güncel değilse önce `notes`) |
| "Nerede kalmıştık?" | `🔮 Companion/Oturumlar/<proje>.md` notunu oku |

## Onay

`digest` çalıştır; `top` listesindeki adayları numaralayıp metinleriyle sohbette
göster (kimlikleri gösterme). Kullanıcı hangilerini onayladığını ya da
reddettiğini kendi sözüyle söyleyince uygula:

```text
{{PYTHON}} -m brain_eleven --vault "{{VAULT_PATH}}" decide --accept <id> ... --reject <id> ...
```

Onaylanan kayıt bir konuya aitse `--topic "<konu>"` ekle: önce `topic` ile
mevcut konu adlarına bak, uyan varsa onu kullan, yoksa kısa bir ad öner ve
kullanıcıya söyle. Farklı konulardaki adayları ayrı `decide` çağrılarıyla onayla.

Kullanıcı açıkça söylemeden hiçbir adayı onaylama ya da reddetme; adı geçmeyen
aday beklemede kalır. Ret geri alınamaz, emin değilsen sor. Metni düzelterek
onaylamak için `review` (tarayıcı açar).

## Konu

Her kayıt bir konuya bağlanabilir; konu yalnız kayıtları notlarda gruplar.

```text
{{PYTHON}} -m brain_eleven --vault "{{VAULT_PATH}}" topic --project-root "$PWD"
{{PYTHON}} -m brain_eleven --vault "{{VAULT_PATH}}" topic "<konu>" <mem_id> ...
```

İlki mevcut konuları ve konusu olmayan kayıtları listeler. Kullanıcı "kayıtları
konulara ayır" derse: konusuz kayıtları oku, az sayıda (proje başına 4–8) kısa
konu adı öner, hangi kaydın hangi konuya gideceğini sohbette göster ve kullanıcı
onaylayınca ikinci komutla yaz. Onaysız konu yazma.

## Kaydet

Yalnız açık bir karar, ders, gözlem ya da açık iş kaydedilir; sohbetin tamamı
ya da tahmin kaydedilmez. Metin tek başına anlaşılır olsun ve NEDEN'i içersin.

```text
{{PYTHON}} "{{VAULT_PATH}}/scripts/remember.py" --vault "{{VAULT_PATH}}" --project-root "$PWD" --type <decision|lesson|observation|open_loop> --content "<metin>"
```

## İş sonucu kaydı

Anlamlı bir iş bittiğinde (PR açıldı, hata çözüldü, karar uygulandı) tek bir
kayıt bırak:

```text
{{PYTHON}} -m brain_eleven --vault "{{VAULT_PATH}}" receipt "<ne bitti, bir iki cümle>" --next "<sıradaki adım>" --source <göreli/yol> --source <#PR veya commit> --project-root "$PWD" --client claude
```

Kaynaklar göreli yol, URL, commit id ya da `#numara` olur; tam dosya yolu
yazılmaz. Aynı kayıt iki kez gönderilirse kopya oluşmaz. Küçük ara adımlar
için kayıt açma; oturum başına birkaç anlamlı sonuç yeter.

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
