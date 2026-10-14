# Brain-Eleven

Eleven'in yerel ikinci beyni. Claude Code ve Codex oturumlarını hook'larla
yakalar, oturumlardan karar ve dersleri çıkarır, sahibin onayından geçenleri
hafızaya yazar ve her yeni oturumda/istemde ilgili hafızayı bağlama ekler.

## Ne yapar

- **Yakalama:** `SessionStart`, `UserPromptSubmit`, `Stop`, `SessionEnd`
  hook'ları oturum dökümlerini kuyruğa alır. Ana kaynak, oturum özetlerindeki
  hata/çözüm maddeleri ve sahibin açık kararlarıdır. Yapıştırılan çıktı,
  belge ve harness mesajları sahip sözü sayılmaz.
- **Ayıklama:** Kurallar ve yerel model kuyruktaki çöpü eler; kalanlar
  inceleme ekranına (`review`) ya da `digest` özetine düşer. Kişi onayı
  olmadan yazılan kayıtlar 14 gün deneme süresinde izlenir.
- **Hatırlama:** Her istemde uygun hafızalar yerel embedding ile kısa
  listeye alınır, cross-encoder ile sıralanır (~1 sn). Başka projelerin en
  ilgili 3 karar/dersi kaynak etiketiyle eklenebilir (`cross-project ON`).
- **Proje çalışması:** `project add` bir klasörü yakalamaya kaydeder,
  `study` bir projeyi ya da GitHub reposunu okuyup karar/ders önerir.

## Kurulum

```bash
pip install -r requirements.txt
python -m brain_eleven --vault <vault> install                  # hook'ları kurar
python -m brain_eleven --vault <vault> project add <proje-klasörü>  # her proje için
python -m brain_eleven --vault <vault> doctor
```

Yeni kurulum doğrudan `ACTIVE` modda başlar ve her yakalanan hafıza sahibin
onayına düşer (`approval ON`). Eski kurulumlar `SHADOW`'dan şu komutla çıkar:

```bash
python -m brain_eleven --vault <vault> rollout ACTIVE
```

## Günlük kullanım

| Komut | Ne işe yarar |
|---|---|
| `doctor` | Kurulum ve hook sağlığı |
| `review` | Onay bekleyen hafızalar (tarayıcıda) |
| `digest` | Günün en değerli adayları |
| `recap --days 7` | Son günlerin oturumları ve yeni hafızaları (model çağırmaz; `--since/--until YYYY-AA-GG`, `--project`) |
| `profile [normal\|economical\|manual]` | Bağlam tüketimi: normal (oturum başı + her istem), ekonomik (yalnız oturum başı, en çok 2000 karakter), manuel (hiç). Yakalama her modda sürer. |
| `project add <klasör>` | Projeyi yakalamaya kaydet |
| `study <klasör veya repo>` | Projeden karar/ders çıkar |
| `notes` | Hafızanın okunur notlarını şimdi yeniden yaz (`🔮 Companion/Hafıza/`; servis değişince kendisi de yeniler) |
| `recall-probe` | 5 soruluk hatırlama testi |
| `measure` | Gerçek kullanım ölçümü |
| `retire <id>` | Bir hafızayı iptal et (silmeden) |

Tüm komutlar: `python -m brain_eleven --help`.

## Geliştirme

```bash
pip install pytest
python -m pytest tests -q
```

Mimari: [ARCHITECTURE.md](ARCHITECTURE.md). Durum ve sıradaki işler:
[NEXT.md](NEXT.md).
