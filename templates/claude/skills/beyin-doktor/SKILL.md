---
name: beyin-doktor
description: Brain-Eleven çalışmıyor gibi göründüğünde kullan — bağlam gelmiyor, oturum yakalanmıyor, "Brain-Eleven kullanılamıyor" uyarısı, hafıza eksik ya da yanlış görünüyor.
---

# Beyin doktoru

Önce ölç, sonra düzelt. Komut öneki:

```text
{{PYTHON}} -m brain_eleven --vault "{{VAULT_PATH}}" <komut>
```

## 1. Teşhis

`doctor` çalıştır ve JSON'u oku. `status: READY` ise kurulum sağlam; sorun
bağlamın içeriğindedir (adım 3).

| Alan | Sorun | Çözüm |
|---|---|---|
| `dependencies` içinde `false` | paket eksik | `{{PYTHON}} -m pip install -r "{{VAULT_PATH}}/requirements.txt"` |
| `clients.<x>.configured: false` | hook kurulu değil ya da ayar dosyası değişmiş | `install` (kullanıcıya hook güven onayını yapması gerektiğini söyle) |
| `mode: OFF` | sistem kapalı | `rollout ACTIVE` |
| `mode: SHADOW` | yakalar ama bağlam vermez | `rollout ACTIVE` |
| `service: STOPPED` | servis kapalı | normal; ilk hook başlatır. Hemen gerekiyorsa `status` |
| `last_hook.status: DEGRADED` | son hook hata verdi | adım 2 |

## 2. Yakalama

`{{VAULT_PATH}}/.brain-eleven/runtime/last-capture-claude.json` (ya da `-codex`)
dosyasındaki `outcome`:

- `CWD_NOT_REGISTERED` → bu klasör kayıtlı değil: `project add "$PWD"`.
- `MODE_OFF` → `rollout ACTIVE`.
- `TRANSCRIPT_NOT_FOUND` / `TRANSCRIPT_PROVENANCE_*` → istemci döküm klasörü
  güvenilen kökler dışında; kullanıcıya bildir, kendi başına ayarı değiştirme.
- `QUEUED` / `PROCESSED` → yakalama çalışıyor; adaylar `digest` ile görünür.

## 3. Hatırlama

- `recall-probe` → 5 soruluk test. Düşükse `bootstrap-explain` hangi hafızanın
  neden bağlama girmediğini söyler.
- `profile` → `manual` ise bilinçli olarak bağlam verilmiyor.
- Onay bekleyen çok aday varsa (`digest`) hafıza eksik görünür; kullanıcıya
  `review` ekranını öner.

## Kurallar

- Hafıza dosyalarını (`.brain-eleven/`) elle düzenleme ya da silme.
- Mod, onay (`approval`) ve profil değişikliklerini kullanıcıya söyleyerek yap.
- Bulduğun sorunu ve yaptığın değişikliği kısa özetle.
