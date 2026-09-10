---
type: decision
title: Middleware Patterns - Composable Request Processing
category: Backend Patterns & Architecture
status: active
created: 2026-08-28
source: expressjs/express (Hamle 5)
tags: [middleware, composition, request-pipeline, express, nodejs]
---

# Middleware Architecture Patterns

**Pattern:** Composable Request Processing Pipeline

## Middleware Execution Order

```
Request → Auth → Logging → Validation → Rate Limit → Handler → Error → Response

Each middleware:
  (req, res, next) => {
    // Pre-processing
    next() // Pass to next middleware
    // Post-processing
  }
```

## Three Core Middleware Types

**1. Preprocessing Middleware (before handler)**
```javascript
// Auth middleware
app.use((req, res, next) => {
  const token = req.headers.authorization
  if (!token) return res.status(401).send('No token')
  
  req.user = verifyToken(token)
  next() // Continue to next middleware
})

// Logging middleware
app.use((req, res, next) => {
  console.log(`${req.method} ${req.path}`)
  next()
})
```

**2. Route Handler**
```javascript
app.post('/data', (req, res) => {
  res.json({ processed: true })
})
```

**3. Error Handling Middleware (after all routes)**
```javascript
// Must have 4 parameters to be error handler!
app.use((err, req, res, next) => {
  console.error(err.stack)
  res.status(500).json({ error: err.message })
})
```

## Critical Pitfalls

```
❌ Forgetting next()
  Request hangs forever

❌ Calling next() after res.send()
  "Headers already sent" error

❌ Async errors not caught
  try/catch must wrap async middleware
  
✓ Proper error handling:
  app.use(async (req, res, next) => {
    try {
      await someAsync()
      next()
    } catch (err) {
      next(err) // Pass to error handler
    }
  })
```

## Composition Pattern

```javascript
// Stack middleware conditionally
const authMiddleware = (req, res, next) => { ... }
const validateBody = (req, res, next) => { ... }
const rateLimit = (req, res, next) => { ... }

// Route-specific middleware
app.post('/api/user', 
  authMiddleware,
  validateBody,
  rateLimit,
  (req, res) => { ... }
)

// Global middleware ordering matters!
app.use(rateLimit)    // First (protects all routes)
app.use(authMiddleware) // Second (checks auth)
app.use(apiRoutes)    // Third (route handlers)
app.use(errorHandler) // Last (catches all errors)
```

## Request Context Pattern

```javascript
// Store request-scoped data
app.use((req, res, next) => {
  req.id = generateRequestId()
  req.startTime = Date.now()
  next()
})

// Access in handlers
app.get('/data', (req, res) => {
  console.log(`[${req.id}] Processing`)
  res.json({ requestId: req.id })
})
```

---

**Bağlantılar:** [[hamle5-frontend-001-react-fiber]]
