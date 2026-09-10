---
type: decision
title: Factory Pattern - Decoupling Object Creation
category: Design Patterns
status: active
created: 2026-08-27
source: ochococo/Design-Patterns-In-Swift
tags: [design-patterns, factory, creational, decoupling]
---

# Factory Pattern

**Pattern:** Separating Instantiation from Usage

## Karar

Object creation logic'i dedicated factory class'a taşı, client code'u concrete classes'ten izole et.

## Neden?

```
❌ Direct instantiation (tightly coupled)
if (type == "PaymentCreditCard") {
  return CreditCardPayment()
} else if (type == "PaymentPaypal") {
  return PayPalPayment()
}
// Yeni payment type ekleme → client code değiştir

✓ Factory pattern (loose coupling)
payment = PaymentFactory.create(type)
// Yeni type → sadece factory değiştir
```

## Üç Varyant

**1. Simple Factory**
```
class PaymentFactory {
  static create(type) {
    if type == "card" → CreditCard()
    if type == "paypal" → PayPal()
  }
}
```

**2. Factory Method (Subclasses)**
```
abstract class Payment {
  abstract create()
}

class CardPaymentFactory extends Payment {
  create() → CreditCard()
}
```

**3. Abstract Factory (Families)**
```
UIFactory.createButton()  → WindowsButton / MacButton
UIFactory.createCheckbox() → WindowsCheckbox / MacCheckbox
```

## Avantajları

- ✅ Decouples client from concrete classes
- ✅ Adds new types without modifying client
- ✅ Centralizes object creation logic
- ✅ Enables runtime type determination

## Ne Zaman Kullan?

- ✓ Multiple implementations of interface
- ✓ Type determined at runtime
- ✓ Object creation is expensive/complex
- ✓ Framework-level abstraction

---

**Bağlantılar:** [[github-harvest-010-builder-pattern]], [[github-harvest-011-singleton-monostate]]
