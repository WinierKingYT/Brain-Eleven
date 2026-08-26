---
type: decision
title: promackro - Macro Scheduler Automation
status: active
created: 2026-08-27
updated: 2026-08-27
tags: [promackro, automation, decision]
source: git log (8 commits, 2026-08-26)
---

# promackro - Macro Automation Kararları

**Proje:** Keyboard macro scheduling ve AutoHotkey v2 entegrasyonu  
**Durum:** aktif geliştirme (8 commits)

## Ana Kararlar (git log'dan çıkarılan)

1. **Macro Scheduler Control Exposure** — Kullanıcı-facing API
2. **AutoHotkey v2 Export** — Standart export formatı
3. **Autosave Recovery Lifecycle** — Graceful recovery
4. **CSV Macro Import** — Batch import workflow
5. **Step Retries + Fallback Jumps** — Error handling
6. **Browser Actions Without Target Window** — Flexibility
7. **Release Packaging to CI** — Automated builds

## İmplikasyon

- AutoHotkey v2 native execution
- CSV import: bulk macro definition
- Retry logic: robust automation
- CI-driven release (no manual packaging)
