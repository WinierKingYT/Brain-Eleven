---
type: decision
title: REST API Design Standards
category: Architecture & API Design
status: active
created: 2026-08-27
source: zalando/restful-api-guidelines (Hamle 4)
tags: [api, rest, standards, conventions, design]
---

# REST API Design Standards

**Pattern:** RFC 7807 Error Format + HTTP Status Codes

## Endpoint Naming Convention

```
✓ Resources: /orders, /users, /products
✓ Hierarchical: /orders/{id}/items
✓ Queries: /orders?status=pending&limit=10
✗ Verbs: /getOrders, /createOrder (anti-pattern)
```

## HTTP Status Codes

| Code | Meaning | When |
|------|---------|------|
| 200 | OK | Request succeeded |
| 201 | Created | Resource created |
| 204 | No Content | Success, no body |
| 400 | Bad Request | Invalid input |
| 401 | Unauthorized | Auth required |
| 403 | Forbidden | Auth OK, not allowed |
| 404 | Not Found | Resource missing |
| 409 | Conflict | Duplicate, state conflict |
| 429 | Too Many Requests | Rate limited |
| 500 | Server Error | Server fault |

## Error Response Format (RFC 7807)

```json
{
  "type": "https://api.example.com/errors/invalid-order",
  "title": "Invalid Order State",
  "status": 409,
  "detail": "Order is already shipped",
  "instance": "/orders/123",
  "timestamp": "2026-08-27T12:34:56Z"
}
```

## Pagination Standards

**Offset-based (simple):**
```
GET /orders?offset=0&limit=10
```

**Cursor-based (scalable):**
```
GET /orders?cursor=abc123&limit=10
Response: {
  "data": [...],
  "cursor": "next-cursor-xyz"
}
```

## API Versioning

**URL versioning:**
```
/v1/orders, /v2/orders (clear but bulky)
```

**Header versioning:**
```
Accept: application/vnd.company.v2+json (clean but hidden)
```

---

**Bağlantılar:** [[hamle4-004-api-idempotency]]
