---
type: decision
title: Hexagonal Architecture - Ports and Adapters Folder Structure
category: Architecture & API Design
status: active
created: 2026-08-27
source: Sairyss/domain-driven-hexagon (Hamle 4)
tags: [architecture, hexagonal, ports, adapters, folder-structure]
---

# Hexagonal Architecture Folder Layout

**Pattern:** Technology-Independent Domain

## Folder Structure

```
project/
├── src/
│   ├── domain/                 ← Business logic (NO imports from adapters)
│   │   ├── entities/           Entity, Aggregate Root, Value Object
│   │   ├── value-objects/
│   │   ├── services/           Business logic (Domain Service)
│   │   ├── repositories/       Interface (PORT)
│   │   └── events/             Domain events
│   │
│   ├── application/            ← Use cases, orchestration
│   │   ├── services/           Application service (UseCase)
│   │   ├── dto/                Data Transfer Objects
│   │   └── ports/              Interface definitions (PORTS)
│   │
│   ├── adapters/               ← External system integration
│   │   ├── http/               REST API (ADAPTER)
│   │   │   └── controllers/
│   │   ├── persistence/        Database (ADAPTER)
│   │   │   └── repositories/   Implement IRepository
│   │   ├── messaging/          Kafka/RabbitMQ (ADAPTER)
│   │   └── external-services/  API integrations
│   │
│   └── shared/                 ← Common utilities
│       ├── utils/
│       └── constants/
```

## Dependency Rule

```
Domain → ← Application → ← Adapters
        (inversion)      (implements)

Domain has NO dependencies
Application depends on Domain (via ports/interfaces)
Adapters depend on Application (implement interfaces)

Example:
- Domain: interface IOrderRepository
- Application: class CreateOrderUseCase(IOrderRepository repo)
- Adapter: class PostgresOrderRepository implements IOrderRepository
```

## Swapping Implementations

```
Development: In-memory repository
test {
  orderRepo = new InMemoryOrderRepository()
  useCase = new CreateOrderUseCase(orderRepo)
  result = useCase.execute(data)
}

Production: PostgreSQL repository
container.bind(IOrderRepository).to(PostgresOrderRepository)
useCase = container.get(CreateOrderUseCase)
```

---

**Bağlantılar:** [[hamle4-018-ddd-bounded-contexts]], [[github-harvest-014-hexagonal-architecture]]
