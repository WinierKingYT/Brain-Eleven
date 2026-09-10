---
type: decision
title: Decorator Pattern - Runtime Behavior Extension
category: Design Patterns
status: active
created: 2026-08-27
source: ochococo/Design-Patterns-In-Swift
tags: [design-patterns, decorator, structural, composition]
---

# Decorator Pattern

**Pattern:** Flexible Behavior Extension Without Inheritance

## Karar

Object'e runtime'da yeni responsibility ekle, inheritance'a gitmeden. Wrapping approach kullan.

## Inheritance Problem

```
❌ Inheritance (rigid)
Coffee
  ├── CoffeeWithMilk extends Coffee
  ├── CoffeeWithSugar extends Coffee
  ├── CoffeeWithMilkAndSugar extends Coffee (combinatorial explosion)
  └── CoffeeWithMilkSugarWhipped...
  
// 5 options × 5 combinations = Explosion!
```

## Decorator Solution

```
✓ Composition (flexible)
coffee = Coffee()
  .with(Milk())
  .with(Sugar())
  .with(Whipped())

// 5 options = 5 classes, not 2^5 combinations
```

## Implementation

```java
abstract class CoffeeDecorator {
  protected Coffee coffee;
  
  CoffeeDecorator(Coffee c) { coffee = c; }
  abstract int cost();
  abstract String description();
}

class MilkDecorator extends CoffeeDecorator {
  cost() { return coffee.cost() + 50; }
  description() { return coffee.description() + ", milk"; }
}
```

## Composition Over Inheritance

| Inheritance | Decorator |
|-------------|-----------|
| Rigid hierarchy | Flexible chains |
| Single parent | Multiple decorators |
| Compile-time | Runtime |
| Class explosion | Scalable |

## Avantajları

- ✅ Avoid class hierarchy explosion
- ✅ Add/remove features at runtime
- ✅ Single Responsibility (each decorator = 1 concern)
- ✅ Open-Closed Principle

## Ne Zaman Kullan?

- ✓ Need many feature combinations
- ✓ Features independent
- ✓ Runtime composition needed
- ✓ Inheritance doesn't model well

---

**Bağlantılar:** [[github-harvest-011-strategy-pattern]], [[github-harvest-012-adapter-pattern]]
