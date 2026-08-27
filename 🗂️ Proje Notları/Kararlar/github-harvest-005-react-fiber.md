---
type: decision
title: React Fiber Architecture
category: Frontend Frameworks
status: active
created: 2026-08-27
source: facebook/react (GitHub Harvest)
tags: [frontend, react, rendering, fiber, reconciliation, scheduling]
---

# React Fiber Architecture

**Pattern:** Incremental Rendering with Priority Scheduling

## Karar

React 16+ render process'i "fiber" adlı küçük parçalara bölerek, yoğun işleri duraklatıp user interactions'a yanıt verebilir hale getirdi.

## Fiber Nedir?

```javascript
// Pre-Fiber: Synchronous render (blocking)
render() → reconcile() → update DOM ✓ (ama UI freeze)

// Fiber: Pausable render (responsive)
fiber1 → [pause] → fiber2 → [pause] → fiber3 ✓
```

## Priority Levels

**1. Discrete (Yüksek):** Input events (click, focus)
**2. Continuous (Orta):** Animations, scroll
**3. Background (Düşük):** Data fetching, logging

## Avantajları

- ✅ 60fps responsive UI (herkes mutlu)
- ✅ Long tasks parçalara bölünür
- ✅ Mobile cihazlarda daha iyi
- ✅ Async rendering hazır

## Dezavantajları

- ✗ Daha karmaşık codebase
- ✗ Debugging zor
- ✗ `getDerivedStateFromProps` broke
- ✗ Hook dependency arrays hata kaynağı

## Multi-Platform Rendering

React Fiber, rendering logic'i abstraction layer (`react-reconciler`) ile host environment'dan ayırdı:
- React DOM (web)
- React Native (iOS/Android)
- Skia Canvas, VR, terminal

---

**Bağlantılar:** [[github-harvest-020-vue-reactivity]], [[github-harvest-021-angular-di]]
