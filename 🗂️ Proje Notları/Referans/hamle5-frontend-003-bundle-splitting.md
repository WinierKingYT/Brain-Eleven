---
type: decision
title: Bundle Splitting Strategy - Route-based Code Splitting
category: Frontend Performance & Patterns
status: active
created: 2026-08-28
source: webpack/webpack (Hamle 5)
tags: [bundling, code-splitting, lazy-loading, webpack, performance]
---

# Bundle Splitting Patterns

**Pattern:** Loading Code on Demand

## The Problem

```
Monolithic bundle:
  index.js: 1.2MB
  
Client downloads entire app on first page load:
  - Bundle parse: 500ms
  - Execute: 1000ms
  - Paint: 1500ms
  
Result: Slow first page load (worse for slow networks)
```

## Route-Based Code Splitting

```javascript
import { lazy, Suspense } from 'react'

const HomePage = lazy(() => import('./pages/Home'))
const ProfilePage = lazy(() => import('./pages/Profile'))
const AdminPage = lazy(() => import('./pages/Admin'))

function App() {
  return (
    <BrowserRouter>
      <Suspense fallback={<Spinner />}>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/profile" element={<ProfilePage />} />
          <Route path="/admin" element={<AdminPage />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
```

Bundles created:
```
main.js:      100KB (common)
pages.home:   50KB  (loaded on /)
pages.profile: 80KB (loaded on /profile)
pages.admin:  200KB (loaded on /admin)
```

## Webpack Configuration

```javascript
// webpack.config.js
module.exports = {
  mode: 'production',
  entry: './src/index.js',
  output: {
    filename: '[name].[contenthash].js',
    chunkFilename: '[name].[contenthash].chunk.js',
    path: __dirname + '/dist'
  },
  optimization: {
    splitChunks: {
      chunks: 'all',
      cacheGroups: {
        // vendor code separate
        vendor: {
          test: /[\\/]node_modules[\\/]/,
          name: 'vendors',
          priority: 10
        },
        // common code to shared chunk
        common: {
          minChunks: 2,
          priority: 5,
          name: 'common'
        }
      }
    }
  }
}
```

## Performance Impact

```
Before splitting:
  main.js: 1.2MB
  FCP: 1500ms
  LCP: 2000ms

After splitting:
  main.js: 100KB
  pages.profile: 80KB
  FCP: 300ms (instant)
  LCP: 800ms (when page loads)
```

## Prefetching Strategy

```javascript
// Predict next route and prefetch
<link rel="prefetch" href="/pages.profile.chunk.js" />

// Or programmatically
useEffect(() => {
  // Prefetch on hover or idle time
  if (canHaveFocusVisible('/profile')) {
    requestIdleCallback(() => {
      import('./pages/Profile')
    })
  }
}, [])
```

## Critical vs Non-Critical

```
Critical paths:
  ✓ Home page
  ✓ Login/auth
  ✓ Main user flow
  
Non-critical:
  Admin panels (lazy load)
  Analytics (defer)
  Help modals (on-demand)
```

---

**Bağlantılar:** [[hamle5-frontend-004-render-optimization]]
