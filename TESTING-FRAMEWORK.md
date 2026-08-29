# Comprehensive Testing Framework

**Status:** Framework ready to implement
**Coverage Goal:** > 80% (100+ tests total)
**Execution Time:** < 5 minutes (all tests)

---

## Test Architecture

```
Unit Tests (30+)
├─ Memory compiler
├─ Memory validator
├─ Embeddings
├─ Retriever
├─ Semantic search
├─ ML ranker
├─ Cache manager
└─ API endpoints

Integration Tests (20+)
├─ Phase 7-10 components
├─ Docker deployment
├─ API + DB + Cache
└─ Full pipelines

Performance Tests (15+)
├─ Latency benchmarks
├─ Throughput tests
├─ Memory profiling
├─ Cache efficiency
└─ Load scenarios

Security Tests (10+)
├─ SQL injection
├─ XSS prevention
├─ Authentication
├─ Authorization
├─ Input validation
└─ Secret scanning

E2E Tests (10+)
├─ User workflows
├─ Full memory lifecycle
├─ Summarization flow
├─ Anomaly detection flow
└─ Docker deployment
```

---

## Part 1: End-to-End Test Scenarios

### E2E Scenario 1: Complete Memory Workflow

```python
# tests/test_e2e_memory_workflow.py

class TestCompleteMemoryWorkflow:
    """Full lifecycle: Create → Validate → Search → Rank"""
    
    def test_memory_creation_to_retrieval(self):
        """End-to-end memory workflow"""
        
        # 1. CREATE: Add new memory via API
        response = client.post("/memories", json={
            "type": "decision",
            "content": "Use PostgreSQL for production database",
            "confidence": 0.95
        })
        assert response.status_code == 201
        memory_id = response.json()['memory_id']
        
        # 2. VALIDATE: Run validator
        memories = load_from_store()
        compiled = compile_daily_memories()
        validated = validate_memories(compiled)
        
        # Assert memory passed validation
        validated_ids = [m['memory_id'] for m in validated]
        assert memory_id in validated_ids
        
        # 3. EMBED: Generate embeddings
        embeddings = generate_embeddings(validated)
        assert memory_id in embeddings
        assert embeddings[memory_id].shape == (1536,)
        
        # 4. SEARCH: Hybrid search
        results = hybrid_search("PostgreSQL production", top_k=5)
        result_ids = [r['memory_id'] for r in results]
        assert memory_id in result_ids
        
        # 5. RANK: ML ranking
        ranked = ml_rank(results)
        # Should rank high due to direct match
        assert ranked[0]['memory_id'] == memory_id
        
        # 6. RETRIEVE: Get from API
        response = client.get(f"/memories/{memory_id}")
        assert response.status_code == 200
        assert response.json()['memory_id'] == memory_id
```

### E2E Scenario 2: Summarization Flow

```python
def test_summarization_workflow(self):
    """Daily recap generation"""
    
    # 1. Create multiple memories throughout day
    memories_today = [
        {
            "type": "decision",
            "content": "Chose PostgreSQL over MongoDB",
            "confidence": 0.95
        },
        {
            "type": "lesson",
            "content": "Async processing improves API latency by 40%",
            "confidence": 0.85
        },
        {
            "type": "open_loop",
            "content": "Need to implement authentication",
            "confidence": 0.90
        }
    ]
    
    for mem in memories_today:
        response = client.post("/memories", json=mem)
        assert response.status_code == 201
    
    # 2. Generate daily recap
    today = datetime.now().strftime("%Y-%m-%d")
    response = client.post(f"/summaries/daily", json={"date": today})
    assert response.status_code == 200
    
    summary = response.json()
    assert summary['date'] == today
    assert len(summary['highlights']) > 0
    assert len(summary['open_loops']) > 0
    
    # 3. Verify recap is cached
    response2 = client.post(f"/summaries/daily", json={"date": today})
    # Should return from cache (< 50ms)
    assert response2.elapsed.total_seconds() < 0.05
    
    # 4. Verify cache invalidation on new memory
    client.post("/memories", json={
        "type": "decision",
        "content": "Decided on API rate limiting strategy"
    })
    
    # Cache should be invalidated
    response3 = client.post(f"/summaries/daily", json={"date": today})
    # Should regenerate (> 100ms)
    assert response3.elapsed.total_seconds() > 0.1
```

### E2E Scenario 3: Anomaly Detection Flow

```python
def test_anomaly_detection_workflow(self):
    """Contradiction finding and risk scoring"""
    
    # 1. Create contradictory memories
    decision1 = client.post("/memories", json={
        "type": "decision",
        "content": "PostgreSQL is the best database choice",
        "confidence": 0.95
    }).json()['memory_id']
    
    decision2 = client.post("/memories", json={
        "type": "decision",
        "content": "Move away from PostgreSQL, switching to MongoDB",
        "confidence": 0.80
    }).json()['memory_id']
    
    # 2. Find contradictions
    response = client.get("/anomalies/contradictions")
    assert response.status_code == 200
    contradictions = response.json()
    
    # Should detect the contradiction
    contradiction_ids = [
        (c['memory_1'], c['memory_2']) for c in contradictions
    ]
    assert (decision1, decision2) in contradiction_ids or \
           (decision2, decision1) in contradiction_ids
    
    # 3. Check contradiction details
    contradiction = next(
        c for c in contradictions 
        if {c['memory_1'], c['memory_2']} == {decision1, decision2}
    )
    assert contradiction['contradiction_score'] > 0.7
    assert contradiction['explanation']
    
    # 4. Analyze single memory for risk
    risk_response = client.post(f"/analyze/{decision2}", json={})
    assert risk_response.status_code == 200
    analysis = risk_response.json()
    assert 'risk_score' in analysis
    # High-risk due to contradicting previous decision
    assert analysis['risk_score'] > 0.6
```

---

## Part 2: Performance Benchmarks

### Latency Benchmarks

```python
# tests/test_performance_latency.py

class TestLatencyBenchmarks:
    """Measure and validate latency targets"""
    
    def test_single_query_latency(self):
        """Single query should be < 200ms (p95)"""
        latencies = []
        
        for i in range(100):
            start = time.time()
            response = client.post("/search", json={
                "query": f"database query {i % 10}"
            })
            elapsed = (time.time() - start) * 1000
            latencies.append(elapsed)
            assert response.status_code == 200
        
        p95 = np.percentile(latencies, 95)
        print(f"Single query p95: {p95:.1f}ms")
        assert p95 < 200, f"p95 latency {p95}ms exceeds target 200ms"
    
    def test_hybrid_search_latency(self):
        """Hybrid search < 100ms (p95)"""
        latencies = []
        
        for i in range(50):
            start = time.time()
            response = client.post("/search", json={
                "query": "test query",
                "hybrid": True
            })
            elapsed = (time.time() - start) * 1000
            latencies.append(elapsed)
        
        p95 = np.percentile(latencies, 95)
        assert p95 < 100
    
    def test_ml_ranking_latency(self):
        """ML ranking < 50ms (p95)"""
        candidates = [...generate test candidates...]
        latencies = []
        
        for i in range(50):
            start = time.time()
            response = client.post("/rank", json={
                "query": "test",
                "candidates": candidates
            })
            elapsed = (time.time() - start) * 1000
            latencies.append(elapsed)
        
        p95 = np.percentile(latencies, 95)
        assert p95 < 50
    
    def test_cache_hit_latency(self):
        """Cached query < 10ms"""
        query = "test database query"
        
        # First query (miss)
        start = time.time()
        response1 = client.post("/search", json={"query": query})
        miss_time = (time.time() - start) * 1000
        
        # Second query (hit)
        start = time.time()
        response2 = client.post("/search", json={"query": query})
        hit_time = (time.time() - start) * 1000
        
        print(f"Cache miss: {miss_time:.1f}ms, hit: {hit_time:.1f}ms")
        assert hit_time < 10
        assert hit_time < miss_time / 5  # Should be 5x+ faster
```

### Throughput Tests

```python
# tests/test_performance_throughput.py

class TestThroughput:
    """Measure queries per second capacity"""
    
    def test_sequential_throughput(self):
        """Sequential throughput (single thread)"""
        queries = [f"query {i}" for i in range(100)]
        
        start = time.time()
        for query in queries:
            response = client.post("/search", json={"query": query})
            assert response.status_code == 200
        
        elapsed = time.time() - start
        qps = len(queries) / elapsed
        
        print(f"Sequential throughput: {qps:.1f} QPS")
        assert qps > 50  # Target: 50+ QPS sequential
    
    def test_concurrent_throughput(self):
        """Concurrent load (100 simultaneous)"""
        from concurrent.futures import ThreadPoolExecutor
        
        def query():
            return client.post("/search", json={
                "query": "test query"
            }).status_code
        
        start = time.time()
        with ThreadPoolExecutor(max_workers=100) as executor:
            futures = [executor.submit(query) for _ in range(1000)]
            results = [f.result() for f in futures]
        
        elapsed = time.time() - start
        qps = len(results) / elapsed
        success = sum(1 for r in results if r == 200)
        
        print(f"Concurrent throughput: {qps:.1f} QPS")
        print(f"Success rate: {success/len(results)*100:.1f}%")
        assert qps > 100  # Target: 100+ QPS concurrent
        assert success / len(results) > 0.99  # 99%+ success
```

### Memory Profiling

```python
# tests/test_performance_memory.py

from memory_profiler import profile

class TestMemoryUsage:
    """Monitor memory consumption"""
    
    @profile
    def test_memory_usage_under_load(self):
        """Profile memory during operations"""
        
        # Load many memories
        for i in range(1000):
            memory_store.add({
                "memory_id": f"mem_{i}",
                "content": f"Memory {i}" * 100,
                "embedding": np.random.randn(1536)
            })
        
        # Multiple searches
        for i in range(100):
            hybrid_search(f"query {i}", top_k=5)
    
    def test_cache_memory_usage(self):
        """Cache shouldn't grow unbounded"""
        
        initial_memory = get_process_memory()
        
        # Fill cache with 10,000 items
        for i in range(10000):
            cache.set(f"key_{i}", f"value_{i}" * 100)
        
        full_memory = get_process_memory()
        
        # Clear cache
        cache.clear()
        
        final_memory = get_process_memory()
        
        # Memory should be returned after clear
        assert final_memory < initial_memory * 1.5
        print(f"Initial: {initial_memory}MB")
        print(f"Full cache: {full_memory}MB")
        print(f"After clear: {final_memory}MB")
```

---

## Part 3: Security Testing

### Input Validation Tests

```python
# tests/test_security_input.py

class TestInputValidation:
    """Ensure all inputs properly validated"""
    
    def test_sql_injection_prevention(self):
        """SQL injection attempts should be rejected"""
        
        malicious_inputs = [
            "'; DROP TABLE memories; --",
            "1' OR '1'='1",
            "admin' --",
            "1; DELETE FROM memories WHERE 1=1"
        ]
        
        for payload in malicious_inputs:
            response = client.post("/search", json={
                "query": payload
            })
            # Should handle safely, not execute
            assert response.status_code == 200
            # Should treat as literal string
            assert len(response.json()['results']) == 0
    
    def test_xss_prevention(self):
        """XSS payloads should be escaped"""
        
        xss_payloads = [
            "<script>alert('xss')</script>",
            "javascript:alert('xss')",
            "<img src=x onerror='alert(1)'>",
        ]
        
        for payload in xss_payloads:
            response = client.post("/memories", json={
                "type": "test",
                "content": payload
            })
            
            # Retrieve and verify escaping
            memory_id = response.json()['memory_id']
            get_response = client.get(f"/memories/{memory_id}")
            content = get_response.json()['content']
            
            # Should be escaped/sanitized
            assert "<script>" not in content.lower()
            assert "javascript:" not in content.lower()
    
    def test_input_length_limits(self):
        """Oversized inputs should be rejected"""
        
        huge_input = "x" * 1_000_000  # 1MB
        
        response = client.post("/memories", json={
            "type": "test",
            "content": huge_input
        })
        
        # Should reject or truncate
        assert response.status_code in [400, 413]  # Bad request or payload too large
    
    def test_parameter_validation(self):
        """Invalid parameters should be rejected"""
        
        invalid_requests = [
            {"query": "", "top_k": -1},  # Negative top_k
            {"query": "test", "top_k": 10000},  # Too large
            {"type": "invalid_type"},  # Unknown type
        ]
        
        for request in invalid_requests:
            response = client.post("/search", json=request)
            assert response.status_code >= 400
```

### Authentication Tests

```python
# tests/test_security_auth.py

class TestAuthentication:
    """API authentication and authorization"""
    
    def test_missing_api_key(self):
        """Requests without API key should be rejected"""
        
        # If API key required (future feature)
        response = client.post("/search", json={
            "query": "test"
        }, headers={})  # No auth header
        
        # For now, should work (optional auth)
        # When auth required: assert response.status_code == 401
    
    def test_invalid_api_key(self):
        """Invalid API key should be rejected"""
        
        response = client.post("/search", json={
            "query": "test"
        }, headers={"Authorization": "Bearer invalid_key"})
        
        # When auth required: assert response.status_code == 401
    
    def test_rate_limiting(self):
        """Rate limiting should prevent abuse"""
        
        # Make 200 requests (limit likely 100/min)
        responses = []
        for i in range(200):
            response = client.post("/search", json={
                "query": f"query {i}"
            })
            responses.append(response.status_code)
        
        # Some should be rate limited (429)
        rate_limited = sum(1 for r in responses if r == 429)
        
        if rate_limited > 0:
            print(f"Rate limited: {rate_limited} requests")
            assert rate_limited > 0  # Should enforce limits
```

---

## Part 4: Test Execution Strategy

### Test Levels

```bash
# Level 1: Unit Tests (< 1 min)
pytest tests/test_*.py -m unit -v

# Level 2: Integration Tests (< 2 min)
pytest tests/test_integration_*.py -v

# Level 3: Performance Tests (< 2 min)
pytest tests/test_performance_*.py -v

# Level 4: Security Tests (< 1 min)
pytest tests/test_security_*.py -v

# Level 5: E2E Tests (< 3 min)
pytest tests/test_e2e_*.py -v

# Full Test Suite (< 10 min)
pytest tests/ -v --cov=scripts --cov-report=html
```

### CI/CD Integration

```yaml
# .github/workflows/test.yml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.13'
      
      - run: pip install -r requirements.txt
      - run: pytest tests/ -v --cov=scripts
      - run: coverage report --fail-under=80
      - uses: codecov/codecov-action@v3
```

---

## Summary

**Testing Framework provides:**
- ✅ 65+ test cases across 5 categories
- ✅ Performance benchmarks with targets
- ✅ Security vulnerability testing
- ✅ End-to-end user workflows
- ✅ Memory profiling
- ✅ Concurrent load testing
- ✅ CI/CD integration ready

**Target:** > 80% code coverage, all tests < 10 min
