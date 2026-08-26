---
type: lesson
title: Step Retries and Fallback Jump Patterns
status: active
created: 2026-08-27
tags: [promackro, automation, lesson]
source: git commit e1b75e0
---

# Retry and Fallback Patterns (promackro)

**Öğretim:** Macro automation'da error handling.

## Bulgu

- Step retries: başarısızlık durumunda N kez retry
- Fallback jumps: conditional branching (başarı/başarısızlık)
- Scheduler API: koşullu yönlendirme

## Çıkarım

Uzun çalışan automation scriptlerinde deterministic error handling
gerekli. Retry + fallback kombinasyonu robustness sağlıyor.
