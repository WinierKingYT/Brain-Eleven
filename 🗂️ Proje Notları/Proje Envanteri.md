---
tags: [envanter]
güncelleme: 2026-08-20
---
# Proje Envanteri

← [[Beyin]]

Aylar sonra bir projeye döndüğünde ilk bakacağın yer. Modelin asla bilemeyeceği şey: hangisi canlı, hangisi uykuda, hangisi korumasız.

| Proje | Yığın | Commit | Son hareket | Gerekçe nerede yaşıyor | Durum |
|---|---|---|---|---|---|
| intelligent-oppenheimer (PromtGen) | TypeScript / React | 265 | 2026-08-19 | **commit gövdeleri** | canlı |
| minecraftmcp | TypeScript / MCP SDK 2.0 | 88 | 2026-08-20 | **20 ADR** (`docs/adr/`) | canlı |
| petsistemi | Java / Paper 1.20.4 | 80 (27 gövdeli) | 2026-08-12 | commit gövdeleri + `docs/` | uykuda |
| Promtsitesi | Next.js / Prisma / Neon | 23 (**0 gövdeli**) | 2026-07-23 | **kod yorumları** + `docs/operations/` | uykuda |
| promackro | C# / WPF | ⚠️ **git yok** | — | README | korumasız |
| mcp_server | C# | ⚠️ **0 takip edilen dosya** | — | README + CHANGELOG | korumasız |
| **beyin2 (bu vault)** | Obsidian | ⚠️ **git yok** | 2026-08-20 | — | **korumasız** |

## Bulgu 1 — gerekçen hep var, ama yeri her projede değişiyor
Dört projede de "neden"i yazmışsın. Ama dördü dört ayrı yerde: ADR, commit gövdesi, kod yorumu, operations runbook.

Sonuç: **tek bir bakılacak yer yok.** Bir kararı hatırlamak istediğinde hangi projede olduğunu bilmen ve o projenin âdetini hatırlaman gerekiyor. Bu vault'un varlık sebebi tam olarak bu — proje üstü tek indeks.

Not: Promtsitesi'nde 23 commit'in **hiçbirinin** gövdesi yok, ama gerekçe kod yorumlarında birinci sınıf yazılmış ([[2026-07-23 - Deploy'da Prisma advisory lock'u kapat]], [[2026-07-22 - Rate limit Upstash yoksa in-memory'e düşsün]]). Yani disiplin var, format tercihi farklı.

## Bulgu 2 — üç proje sürüm kontrolü dışında
- `promackro` — 61 kendi `.cs` dosyası, hiç git yok.
- `mcp_server` — `.git` var ama 0 takip edilen dosya; üstelik `.git` başka bir hesabın (`CodexSandboxOffline`) mülkiyetinde, git "dubious ownership" diye reddediyor. Tam açık kaynak paketlemesi (SECURITY.md, CONTRIBUTING.md, çift dilli README, PR şablonu) diskte duruyor ama hiçbir şey commit edilmemiş.
- `beyin2` — bu vault. 2026-08-20'de 21 not tek tıkla silindi, Geri Dönüşüm Kutusu'ndan **şans eseri** kurtarıldı.

→ İlgili ders: [[Sessizce çalışmayan yedek, yedek değildir]]
→ Açık soru: [[Açık Döngüler]]
