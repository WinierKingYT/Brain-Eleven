---
type: decision
title: Offline-First Sync with Conflict Resolution
category: Mobile Development & Data Management
status: active
created: 2026-08-28
source: mobile-production-systems (Hamle 7)
tags: [mobile, offline-first, sync, conflict-resolution, data-consistency]
---

# Offline-First Sync Architecture

**Pattern:** Local-first data with background sync and automatic conflict resolution.

## The Problem

Mobile networks are unreliable; offline-first apps must work disconnected:
- User edits todo locally → app goes offline → edits lost on crash
- Sync on reconnect → server has different version → conflict
- Resolving conflicts manually breaks UX

## Solution: Local Storage + Queue + Sync

```swift
// iOS: Core Data local storage + background sync

// 1. Local change (immediate)
let todo = TodoEntity(context: coreDataManager.context)
todo.title = "Buy milk"
todo.status = "pending"
todo.syncStatus = "local"  // Mark as not synced
coreDataManager.save()

// 2. Queue for sync
syncQueue.add(SyncOperation(
  type: .create,
  entity: "todo",
  data: todo.toDictionary(),
  timestamp: Date(),
  retries: 0
))

// 3. Sync when online
func syncPendingChanges() {
  for operation in syncQueue.getPending() {
    do {
      let response = try await apiClient.sync(operation)
      
      // Update local record with server ID
      todo.serverId = response.id
      todo.syncStatus = "synced"
      todo.lastSyncedAt = Date()
      coreDataManager.save()
      
      syncQueue.markDone(operation)
    } catch SyncError.conflict {
      // Handle conflict (see below)
      resolveConflict(local: todo, remote: response)
    }
  }
}
```

## Conflict Resolution Strategies

**1. Last-Write-Wins (Simple)**
```swift
// Server wins: overwrites local changes
if remote.updatedAt > local.updatedAt {
  local = remote
} else {
  // Local wins: send to server
  _ = try await api.update(local)
}
```

**2. Merge (Automatic)**
```swift
// Merge independent fields
let merged = TodoEntity(
  title: remote.title,  // Server version
  description: local.description,  // Local version (not modified server-side)
  dueDate: remote.dueDate,
  priority: local.priority
)
```

**3. User-Decides (UX)**
```swift
// Show both versions; user picks
func showConflictResolver(local: Todo, remote: Todo) {
  let alert = UIAlertController(
    title: "Conflict",
    message: "Local and server versions differ",
    preferredStyle: .alert
  )
  
  alert.addAction(UIAlertAction(
    title: "Keep Local",
    handler: { _ in self.resolveLocal(local) }
  ))
  
  alert.addAction(UIAlertAction(
    title: "Use Server",
    handler: { _ in self.resolveRemote(remote) }
  ))
}
```

## Soft Deletes (Better Than Hard Delete)

```swift
// Problem: Hard delete fails to sync
todoRepository.delete(todo)  // ❌ Deleted locally; can't send deletion signal

// Solution: Mark as deleted
todo.isDeleted = true
todo.deletedAt = Date()
todo.syncStatus = "pending"
coreDataManager.save()

// On sync: Server sees isDeleted=true; removes its copy
_ = try await api.update(todo)  // Includes isDeleted=true
```

## Partial Sync Failures

```swift
// Problem: 50 pending operations; operation 30 fails; rest abandon
// Solution: Transaction-like semantics

func syncBatch() {
  let pending = syncQueue.getPending()
  var succeeded = []
  var failed = []
  
  for operation in pending {
    do {
      _ = try await api.sync(operation)
      succeeded.append(operation)
    } catch {
      failed.append(operation)
      // Continue to next; don't abort
    }
  }
  
  syncQueue.remove(succeeded)
  // Re-queue failed operations for next sync attempt
}
```

## Monitoring Sync Status

```swift
// Show user sync progress
let syncStatus = SyncStatus(
  pending: syncQueue.count,
  lastSyncedAt: userDefaults.lastSync,
  isSyncing: backgroundSyncTask.isRunning
)

// UI:
// ✓ Synced 2h ago
// ↻ Syncing 5 changes...
// ⚠ 3 changes pending (offline)
```

---

**Bağlantılar:**
- [[hamle7-mobile-001-mvvm-viewmodel]] (ViewModel state during sync)
- [[hamle6-system-001-event-sourcing]] (event-based sync alternative)
- [[hamle6-testing-001-test-pyramid]] (testing offline scenarios)
