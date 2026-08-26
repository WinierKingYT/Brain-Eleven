---
type: decision
title: petsistemi - Selection-Runtime Separation
status: active
created: 2026-08-27
updated: 2026-08-27
tags: [petsistemi, architecture, decision]
source: docs/adr/0002-selection-runtime-separation.md
---

# Selection-Runtime Separation (petsistemi ADR-0002)

Yapı: pet seçim (stateless, oyuncu input) vs runtime (stateful, yaşam döngüsü) ayrılması.

## İmplikasyon

- Seçim logic oyuncu bağlamı olmadan test edilebilir
- Runtime state sadece active evcil hayvanlara uygulanır
- Lifecycle kontrol merkezi: startup, graceful shutdown
