---
type: lesson
title: Composition Over Inheritance
category: Design Patterns
status: active
created: 2026-08-27
source: ochococo/Design-Patterns-In-Swift
tags: [design-patterns, composition, inheritance, flexibility]
---

# Composition Over Inheritance

## Prensip

Inheritance rigidity'ye ve kombinatorial explosion'a yol açar. Composition ile runtime'da flexible behavior build et.

## Inheritance Problemi

```
Shape
  ├─ Rectangle
  │   ├─ ColoredRectangle
  │   ├─ FilledRectangle
  │   └─ ColoredFilledRectangle ← Combinatorial explosion!
  ├─ Circle
  ├─ Triangle
```

5 shapes × 3 behaviors = 15 classes  
10 shapes × 5 behaviors = 50 classes

## Composition Çözüm

```
Shape (interface)
  ├─ Rectangle
  ├─ Circle
  └─ Triangle

Drawing behavior (separate):
  ├─ ColorBehavior
  ├─ FillBehavior
  └─ StrokeBehavior

// Kullanım:
shape = Rectangle()
  .withColor(Red)
  .withFill(Solid)
  .withStroke(Dashed)
```

## Avantajları

- ✅ No class explosion (n + m instead of n × m)
- ✅ Runtime flexibility (add/remove at will)
- ✅ Single responsibility (each class = 1 concern)
- ✅ Easier testing (mock individual behaviors)
- ✅ Follows Open-Closed Principle

## Dezavantajları Inheritance

- ✗ Fragile base class problem
- ✗ Gorilla/banana problem ("I want banana, I get gorilla and jungle")
- ✗ Deep hierarchies hard to understand
- ✗ Behavior changes break subclasses

## Uygulanabilirlik

Composition tercih edilecek durumlar:
- ✓ Many feature combinations
- ✓ Features independent
- ✓ Runtime behavior changes
- ✓ Type hierarchies deep (>3 levels)

Inheritance still useful:
- ✓ Interface contracts (abstract base)
- ✓ is-a relationship (Dog is-a Animal)
- ✓ Shared state/methods (DRY)

---

**Bağlantılar:** [[github-harvest-010-decorator-pattern]], [[github-harvest-011-strategy-pattern]]
