---
type: decision
title: Image Caching Strategy - Memory + Disk Two-Tier
category: Mobile Development & Performance
status: active
created: 2026-08-28
source: mobile-production-systems (Hamle 7)
tags: [mobile, caching, performance, images, memory-management]
---

# Two-Tier Image Caching

**Pattern:** Fast in-memory cache + persistent disk cache without OOM crashes.

## The Problem

Image-heavy apps (feeds, galleries) cause OOM crashes:
- Memory cache fast but limited (~50MB on low-end Android)
- No cache slow (re-download on each view)
- Disk cache large but slow
- Need balance: speed vs memory vs persistence

## Solution: LRU Memory Cache + Disk Cache

**Android with Glide (Automatic)**

```kotlin
// Glide handles both tiers automatically
Glide.with(context)
  .load("https://example.com/image.jpg")
  .into(imageView)

// Glide's default:
// 1. Memory cache (LRU, ~25% available RAM)
// 2. Disk cache (LRU, 250MB default)
// 3. Network (if not cached)
```

**Manual Two-Tier Implementation**

```swift
class ImageCacheManager {
  private let memoryCache = NSCache<NSString, UIImage>()
  private let diskCache = FileManager.default
  
  func loadImage(url: String) -> UIImage? {
    let cacheKey = url.hashValue
    
    // Tier 1: Memory cache (fast, small)
    if let cached = memoryCache.object(forKey: cacheKey as NSString) {
      return cached
    }
    
    // Tier 2: Disk cache (persistent, larger)
    if let diskImage = loadFromDisk(cacheKey) {
      memoryCache.setObject(diskImage, forKey: cacheKey as NSString)
      return diskImage
    }
    
    // Tier 3: Network (slowest)
    Task {
      let image = try await downloadImage(url)
      
      // Populate both caches
      memoryCache.setObject(image, forKey: cacheKey as NSString)
      saveToDisk(cacheKey, image: image)
    }
    
    return nil  // Return nil; caller shows placeholder
  }
}
```

## Handling Memory Pressure

```swift
// Listen for memory warnings
NotificationCenter.default.addObserver(
  forName: UIApplication.didReceiveMemoryWarningNotification,
  object: nil,
  queue: .main
) { _ in
  // Aggressive cache eviction on low memory
  memoryCache.removeAllObjects()
  log("Memory warning: cleared image cache")
}

// NSCache automatically evicts on memory pressure
// Set max size to limit memory growth
memoryCache.totalCostLimit = 50_000_000  // 50MB max
```

## Disk Cache Cleanup

```swift
func cleanupDiskCache() {
  let cachePath = FileManager.default.urls(
    for: .cachesDirectory,
    in: .userDomainMask
  )[0].appendingPathComponent("images")
  
  guard let files = try? FileManager.default.contentsOfDirectory(
    at: cachePath,
    includingPropertiesForKeys: [.contentModificationDateKey]
  ) else { return }
  
  // Remove files older than 7 days
  let sevenDaysAgo = Date().addingTimeInterval(-7 * 24 * 3600)
  
  for file in files {
    if let modDate = try? file.resourceValues(forKeys: [.contentModificationDateKey]).contentModificationDate,
       modDate < sevenDaysAgo {
      try? FileManager.default.removeItem(at: file)
    }
  }
}
```

## Image Aspect Ratio & Layout Stability

```swift
// Problem: Image loads with no size → causes layout shift
// Solution: Show placeholder with correct aspect ratio

func loadImageWithPlaceholder(
  url: String,
  aspectRatio: CGFloat = 1.0  // e.g., 1.5 for 3:2 images
) {
  // Placeholder same size as final image
  let placeholder = UIImage.placeholder(aspectRatio: aspectRatio)
  imageView.image = placeholder
  imageView.heightAnchor.constraint(
    equalTo: imageView.widthAnchor,
    multiplier: 1 / aspectRatio
  ).isActive = true
  
  // Load actual image
  Task {
    let image = await loadImage(url)
    imageView.image = image  // No layout shift; same size
  }
}
```

## When to Use

✓ **Any app with >10 images** (feed, gallery, product listings)
✓ **Memory-constrained devices** (older iPhones, low-end Android)
✓ **Offline support** (cached images visible without network)

## Production Gotchas

**1. Memory Cache Eviction Timing Unpredictable**
- Low-memory device → cache cleared at unpredictable times
- Image disappears from UI
- **Fix:** Always have fallback; show placeholder if evicted

**2. Disk Cache Can Grow Unbounded**
- No automatic cleanup → cache fills storage
- Device shows "Storage full"
- **Fix:** Implement TTL cleanup; monitor cache size; set max limit

**3. Image Subsampling for Previews vs Full-Res**
- Display 100px thumbnail; cache stores 3000px original
- **Fix:** Use image resizing; cache multiple sizes (thumb, medium, full)

**4. Memory Spike During Image Composition**
- Caching + resizing + filtering happens in memory
- **Fix:** Process images on background thread; avoid main thread blocking

---

**Bağlantılar:**
- [[hamle7-mobile-001-mvvm-viewmodel]] (managing cache in ViewModel)
- [[hamle5-performance-001-flame-graphs]] (profiling memory usage)
- [[hamle6-devops-001-structured-logging-json]] (monitoring cache hits/misses)
