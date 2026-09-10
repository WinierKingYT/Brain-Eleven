---
type: decision
title: Middleware Pipeline Pattern
category: Backend Frameworks
status: active
created: 2026-08-27
source: expressjs/express (GitHub Harvest)
tags: [backend, frameworks, middleware, request-response, express, node.js]
---

# Middleware Pipeline Pattern

**Pattern:** Linear Request/Response Processing Chain

## Karar

Express.js'in en temel pattern'ı: Her middleware request'i işler, next() çağırarak sonrakine geçer. Chain sonunda response gönderilir.

## Flow

```
Request → MW1 → MW2 → MW3 → Handler → Response ← MW3 ← MW2 ← MW1
```

## Ortak Middleware Konfigürasyonu

```javascript
// Sıra önemlidir!
app.use(bodyParser.json())           // Body parsing
app.use(logger())                     // Logging
app.use(authenticate)                 // Auth check
app.use('/api', apiRoutes)            // Routes
app.use(errorHandler)                 // Error handling (sonunda)
```

## Avantajları

- ✅ Basit, lineer mental model
- ✅ Ekosistem (1000+ npm middleware)
- ✅ Hızlı prototipleme
- ✅ Minimal boilerplate

## Dezavantajları

- ✗ Sıra bağımlılıkları (order matters)
- ✗ Debugging zor (implicit flow)
- ✗ Middleware nesting karmaşık
- ✗ Type safety yok (JavaScript)

## Alternatifleri

- **Fastify**: Named hooks (16+ lifecycle points)
- **Django**: WSGI wrapper model
- **Spring Boot**: Annotation-based DI

---

**Bağlantılar:** [[github-harvest-005-hooks-fastify]], [[github-harvest-006-service-container]]
