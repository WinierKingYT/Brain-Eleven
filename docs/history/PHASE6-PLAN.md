# Phase 6: Testing & Optimization

**Objective:** Validate system reliability, prevent regressions, optimize performance

## Scope

### 1. Regression Test Suite (Core)
- **Memory Compiler Tests**
  - Multi-day Daily parsing (date-aware split)
  - Section extraction accuracy
  - Source_id generation format
  - Candidate deduplication

- **Memory Validator Tests**
  - Conflict detection (new vs prior)
  - Fingerprint-based dedup
  - Lifecycle field preservation
  - Quality scoring edge cases

- **Memory Lifecycle Tests**
  - Resolve/supersede operations
  - ULID lookup (not integer ID)
  - Provenance chain tracing
  - Atomic write safety

- **Memory Retriever Tests**
  - Query relevance filtering (5% gate)
  - Combined scoring formula
  - Lifecycle status filtering
  - Top-5 ranking accuracy

### 2. Data Integrity Verification
- **Atomic Persistence Tests**
  - Temp file creation
  - JSON validation
  - Atomic rename
  - Backup creation on overwrite

- **Migration Tests**
  - ULID assignment
  - Fingerprint computation
  - Legacy ID backward compat
  - No data loss on migration

- **Cumulative Store Tests**
  - Prior memory preservation
  - Duplicate detection
  - Lifecycle state restoration
  - Memory count accuracy

### 3. Performance Baseline
- **Memory Compiler**
  - Parse 100 Daily entries: < 2s
  - Extract 500 candidates: < 1s
  - Deduplicate: < 0.5s

- **Memory Validator**
  - Load 500 candidates: < 0.5s
  - Conflict detection: < 1s
  - Quality scoring: < 1s

- **Memory Retriever**
  - Load 500 memories: < 0.5s
  - Single query (100 memories): < 100ms
  - Batch queries (10): < 1s

### 4. CI/CD Integration
- **Pre-commit Hooks**
  - JSON validation
  - Python syntax check
  - File size sanity checks

- **GitHub Actions** (if applicable)
  - Run full test suite
  - Memory integrity check
  - Performance regression detection

### 5. Edge Cases & Stress Tests
- **Compiler Edge Cases**
  - Empty Daily.md
  - Malformed sections
  - Very long entries (>10KB)
  - Special characters in content

- **Validator Edge Cases**
  - No prior memory (first run)
  - Corrupted JSON (recovery)
  - Duplicate decisions (same content)
  - Circular supersessions

- **Retriever Edge Cases**
  - Empty memory store
  - Query with no matches
  - All memories resolved
  - Very similar memories (rank tie)

## Implementation Order

### Week 1: Core Regression Tests
1. Write unit tests for each module
2. Create test fixtures (sample Daily entries)
3. Test migration path (legacy → ULID)
4. Verify cumulative store behavior

### Week 2: Data Integrity
1. Test atomic persistence
2. Simulate crash scenarios (partial writes)
3. Verify backup creation
4. Test recovery from corrupted state

### Week 3: Performance & CI
1. Establish performance baselines
2. Create CI pipeline
3. Add pre-commit hooks
4. Document performance targets

## Test Framework

**Language:** Python (pytest)  
**Coverage Target:** 80%+  
**Test Data:** Sample Daily.md with 30+ entries spanning multiple dates

## Success Criteria

- ✅ All regression tests passing
- ✅ No memory loss in migration
- ✅ Atomic writes verified (no partial data)
- ✅ Performance within baselines (< 5s full pipeline)
- ✅ CI/CD integrated and green
- ✅ Edge cases handled gracefully

## Deliverables

1. `tests/` directory with pytest suite
2. `tests/fixtures/` with sample data
3. `.github/workflows/test.yml` for CI
4. `.pre-commit-config.yaml` for hooks
5. `PERFORMANCE.md` with baselines and results
6. `TESTING.md` with how to run tests

---

**Estimated Effort:** 3-4 sessions  
**Risk Level:** LOW (no production changes, tests only)  
**Next Phase After:** Phase 7 - Advanced Retrieval (Embeddings + ML ranking)
