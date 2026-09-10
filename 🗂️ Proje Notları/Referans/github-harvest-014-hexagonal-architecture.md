---
type: decision
title: Hexagonal Architecture - Ports & Adapters
category: Clean Architecture & DDD
status: active
created: 2026-08-27
source: gsaaraujo/DDD-Clean-Architecture-backend
tags: [clean-architecture, hexagonal, ports-adapters, ddd, framework-agnostic]
---

# Hexagonal Architecture (Ports & Adapters)

**Pattern:** Framework-Independent Domain Logic

## Karar

Domain logic'i framework, database, HTTP handler'dan izole et. Ports (interfaces) ve Adapters (implementations) ile dış bağlantıları handle et.

## Mimarı

```
                    ┌──────────────────────┐
                    │  Domain Logic        │
                    │  (Business Rules)    │
                    └──────────────────────┘
                       ↑         ↑         ↑
                   Ports (interfaces)
                       ↓         ↓         ↓
        ┌──────────┬──────────┬──────────┐
        │          │          │          │
    HTTP Adapter  DB Adapter  Email     Cache
                           Adapter    Adapter
```

## Örnek: UserRepository Port

```java
// Port (interface) - Domain knows this
interface IUserRepository {
  User findById(UserId);
  void save(User);
}

// Adapter 1 - SQLite implementation
class SQLiteUserRepository implements IUserRepository {
  findById(id) { return db.query("SELECT * FROM users WHERE id=?") }
}

// Adapter 2 - PostgreSQL implementation
class PostgresUserRepository implements IUserRepository {
  findById(id) { return postgres.query("SELECT * FROM users WHERE id=?") }
}

// Domain (uses interface, not concrete)
class UserService {
  create(IUserRepository repo, UserData data) {
    User user = User.createNew(data);
    repo.save(user);  // Repository agnostic
  }
}
```

## Avantajları

- ✅ Framework agnostic (switch Next.js → Nuxt)
- ✅ Easy testing (mock adapters)
- ✅ Technology swaps (SQLite → PostgreSQL)
- ✅ Domain logic clean (no framework contamination)

## Dezavantajları

- ✗ More interfaces to maintain
- ✗ Can feel over-engineered for simple CRUD
- ✗ Adapter boilerplate

## Ne Zaman Kullan?

- ✓ Long-lived projects (likely framework change)
- ✓ Complex business logic (framework independence valuable)
- ✓ Multiple backend options (GraphQL, REST, gRPC)
- ❌ Simple apps (prototype, MVP)

---

**Bağlantılar:** [[github-harvest-007-aggregate-root]], [[github-harvest-009-factory-pattern]]
