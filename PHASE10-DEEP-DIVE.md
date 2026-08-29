# Phase 10: Deep Dive - Auto-Summarization & Anomaly Detection

**Status:** 🚀 Currently being implemented by agents
**Depth:** Complete implementation details + architecture

---

## Part 1: Auto-Summarization Engine

### Architecture Overview

```
Memory Store (46+ memories)
    ↓
Memory Filter (by date range)
    ↓
Content Extraction (type, confidence, impact)
    ↓
OpenAI GPT-4 mini (summarization)
    ↓
Structured Output (insights, highlights, trends)
    ↓
Cache & API Response
```

### 1.1 Daily Recap

**Purpose:** Quick daily summary of what was learned/decided

**Input:** All memories from yesterday
**Output:**
```json
{
  "date": "2026-08-29",
  "title": "Daily Recap - August 29",
  "highlights": [
    "Decision 1: ...",
    "Decision 2: ...",
    "Lesson: ..."
  ],
  "insights": [
    "Key learning 1",
    "Key learning 2"
  ],
  "open_loops": [
    "Task 1: needs resolution",
    "Task 2: pending follow-up"
  ],
  "confidence": 0.95
}
```

**Implementation:**
```python
def daily_recap(date: str) -> SummaryResponse:
    # 1. Filter memories from that date
    memories = memory_store.filter_by_date(date)
    
    # 2. Extract key info
    decisions = [m for m in memories if m['type'] == 'decision']
    lessons = [m for m in memories if m['type'] == 'lesson']
    
    # 3. Build prompt for GPT-4 mini
    prompt = f"""
    Summarize these {len(memories)} memories from {date}:
    
    Decisions ({len(decisions)}):
    {format_memories(decisions)}
    
    Lessons ({len(lessons)}):
    {format_memories(lessons)}
    
    Create a brief daily recap with:
    - Top 3 highlights
    - Key insights
    - Open loops to track
    """
    
    # 4. Call OpenAI
    response = openai.ChatCompletion.create(
        model="gpt-4-turbo-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    
    # 5. Parse and structure
    recap = parse_summary(response.choices[0].message.content)
    
    # 6. Cache for 7 days
    cache.set(f"recap:{date}", recap, ttl=604800)
    
    return recap
```

**Cache Strategy:**
- TTL: 7 days (604,800 seconds)
- Key: `recap:YYYY-MM-DD`
- Invalidated: When any memory from that date is updated
- Fallback: Regenerate on cache miss

### 1.2 Weekly Summary

**Purpose:** Identify trends, patterns, and progress

**Input:** All memories from past 7 days
**Output:**
```json
{
  "week": "2026-08-24 to 2026-08-30",
  "title": "Weekly Summary",
  "themes": [
    "Theme 1: Focus area and progress",
    "Theme 2: Challenges overcome",
    "Theme 3: Emerging patterns"
  ],
  "trends": {
    "decision_frequency": 8,
    "learning_rate": 5,
    "risk_incidents": 1,
    "status": "productive"
  },
  "recommendations": [
    "Action 1 based on trends",
    "Action 2 for next week"
  ],
  "metrics": {
    "decisions_made": 8,
    "lessons_learned": 5,
    "problems_solved": 3,
    "new_risks": 1
  }
}
```

**Implementation:**
```python
def weekly_summary(start_date: str, end_date: str) -> WeeklySummary:
    # 1. Get all memories in date range
    memories = memory_store.filter_by_date_range(start_date, end_date)
    
    # 2. Categorize by type
    by_type = categorize(memories)
    
    # 3. Extract trends
    trends = {
        'decision_frequency': len(by_type['decision']),
        'learning_rate': len(by_type['lesson']),
        'risk_incidents': sum(1 for m in by_type['decision'] if m.get('risk_level') == 'high'),
    }
    
    # 4. Build comprehensive prompt
    prompt = f"""
    Analyze these {len(memories)} memories from {start_date} to {end_date}:
    
    Statistics:
    - Decisions: {trends['decision_frequency']}
    - Lessons: {trends['learning_rate']}
    - High-risk items: {trends['risk_incidents']}
    
    Content:
    {format_memories_by_type(by_type)}
    
    Provide:
    1. 3 major themes from the week
    2. Key trends and patterns
    3. Recommendations for next week
    4. Confidence score for summary quality
    """
    
    # 5. Call OpenAI
    response = openai.ChatCompletion.create(
        model="gpt-4-turbo-mini",
        messages=[{"role": "user", "content": prompt}]
    )
    
    # 6. Structure response
    summary = parse_weekly_summary(response)
    
    # 7. Cache for 30 days
    cache.set(f"summary:week:{week_num}", summary, ttl=2592000)
    
    return summary
```

### 1.3 Monthly Review

**Purpose:** Assess progress, identify patterns, plan ahead

**Input:** All memories from past month
**Output:**
```json
{
  "month": "August 2026",
  "title": "Monthly Review",
  "executive_summary": "High-level overview of month",
  "major_decisions": [
    {"decision": "...", "impact": "high", "status": "implemented"}
  ],
  "learning_outcomes": [
    "Outcome 1",
    "Outcome 2",
    "Outcome 3"
  ],
  "progress_metrics": {
    "decisions_implemented": 24,
    "lessons_applied": 12,
    "problems_solved": 15,
    "open_loops_closed": 8,
    "new_open_loops": 5
  },
  "patterns_identified": [
    "Pattern 1: Description and implications",
    "Pattern 2: Description and implications"
  ],
  "recommendations": [
    "Strategic 1",
    "Strategic 2",
    "Tactical 1",
    "Tactical 2"
  ]
}
```

---

## Part 2: Anomaly Detection Engine

### Architecture Overview

```
Memory Store + Embeddings
    ↓
Anomaly Detection Algorithms
├─ Vector Distance Outliers
├─ Semantic Contradictions
├─ Pattern Break Detection
└─ Risk Scoring
    ↓
Findings + Alerts
    ↓
API Response & Logging
```

### 2.1 Contradiction Detection

**Goal:** Find semantically contradictory memories

**Algorithm:**
```
For each memory M:
  Get embedding E_m
  
  For each other memory M':
    Get embedding E_m'
    
    Compute cosine_similarity(E_m, E_m')
    
    If similarity > 0.85 (very similar topic):
      Check if sentiment/recommendation opposite
      If yes: CONTRADICTION FOUND
      
      Score = (similarity * 0.7) + (sentiment_opposition * 0.3)
      Store: (M, M', score, explanation)
```

**Implementation:**
```python
def find_contradictions() -> List[Contradiction]:
    memories = memory_store.get_all_active()
    contradictions = []
    
    for i, mem1 in enumerate(memories):
        emb1 = embeddings.get(mem1['memory_id'])
        if emb1 is None:
            continue
            
        for mem2 in memories[i+1:]:
            emb2 = embeddings.get(mem2['memory_id'])
            if emb2 is None:
                continue
            
            # Check semantic similarity
            similarity = cosine_similarity(emb1, emb2)
            
            if similarity > 0.80:  # Similar topics
                # Check sentiment/recommendation opposition
                sentiment1 = extract_sentiment(mem1['content'])
                sentiment2 = extract_sentiment(mem2['content'])
                
                if sentiments_oppose(sentiment1, sentiment2):
                    contradiction = {
                        'memory_1': mem1['memory_id'],
                        'memory_2': mem2['memory_id'],
                        'similarity': similarity,
                        'contradiction_score': calculate_contradiction_score(
                            similarity, sentiment1, sentiment2
                        ),
                        'explanation': generate_explanation(mem1, mem2),
                        'timestamp': datetime.now().isoformat()
                    }
                    contradictions.append(contradiction)
    
    # Sort by contradiction score
    contradictions.sort(key=lambda x: x['contradiction_score'], reverse=True)
    
    return contradictions
```

**Example Output:**
```json
{
  "contradiction_id": "001",
  "memory_1": {
    "id": "01M155WB9AKKTCZWTFRDDZR4W7",
    "content": "Use PostgreSQL for production - it's the best choice",
    "timestamp": "2026-08-20"
  },
  "memory_2": {
    "id": "01M156CKJAWDPFCPV7RZ011QC0",
    "content": "Move away from PostgreSQL - considering alternatives",
    "timestamp": "2026-08-28"
  },
  "similarity": 0.87,
  "contradiction_score": 0.92,
  "explanation": "Earlier decided PostgreSQL was best, now reconsidering. Major shift in database strategy.",
  "suggested_action": "Review why PostgreSQL preference changed"
}
```

### 2.2 Pattern Break Detection

**Goal:** Identify when behavior deviates from established patterns

**Algorithm:**
```
1. Identify patterns in decision history
   - Decision frequency: decisions/day
   - Risk appetite: average risk level
   - Domain focus: most common topics
   - Confidence: average confidence scores

2. For each new memory:
   - Check against established patterns
   - If deviates significantly: FLAG

3. Calculate deviation score:
   - Frequency deviation: |new_freq - baseline_freq| / baseline_freq
   - Risk deviation: |new_risk - avg_risk| / avg_risk
   - Domain deviation: Is new memory in usual domain?
   - Confidence deviation: |new_conf - avg_conf| / avg_conf
   
   Total score = weighted sum of deviations
```

**Implementation:**
```python
def detect_pattern_breaks(lookback_days: int = 30) -> List[PatternBreak]:
    memories = memory_store.get_active_in_range(lookback_days)
    
    # 1. Calculate baseline patterns
    baseline = calculate_baseline_patterns(memories[:-1])  # Exclude most recent
    
    # 2. Check latest memory against baseline
    latest = memories[-1]
    
    deviations = {
        'frequency': check_frequency_deviation(latest, baseline),
        'risk': check_risk_deviation(latest, baseline),
        'domain': check_domain_deviation(latest, baseline),
        'confidence': check_confidence_deviation(latest, baseline)
    }
    
    total_deviation = weighted_sum(deviations, weights={
        'frequency': 0.25,
        'risk': 0.35,
        'domain': 0.20,
        'confidence': 0.20
    })
    
    if total_deviation > 0.5:  # 50% deviation threshold
        return PatternBreak(
            memory=latest,
            baseline=baseline,
            deviations=deviations,
            severity=calculate_severity(total_deviation)
        )
    
    return []
```

### 2.3 Risk Scoring

**Goal:** Flag potentially risky decisions

**Factors:**
```
Risk Score = 0.3 * confidence_check 
           + 0.2 * decision_impact
           + 0.2 * reversibility
           + 0.15 * stakeholder_complexity
           + 0.15 * unknown_factors

Confidence check:
  - Low confidence (<0.7) = higher risk
  - Missing validation = higher risk

Decision impact:
  - High impact = higher risk
  - Long-term effects = higher risk

Reversibility:
  - Hard to reverse = higher risk
  - No undo option = higher risk

Stakeholder complexity:
  - Many stakeholders = higher risk
  - Cross-team = higher risk

Unknown factors:
  - Explicit unknowns = higher risk
  - Assumptions = higher risk
```

**Implementation:**
```python
def risk_score(memory: Memory) -> float:
    score = 0.0
    
    # Confidence check (0-1, higher = less risky)
    confidence = memory.get('confidence', 0.5)
    score += 0.3 * (1.0 - confidence)  # Inverted: low confidence = high risk
    
    # Decision impact (0-1)
    impact = extract_impact_level(memory['content'])
    score += 0.2 * impact
    
    # Reversibility (0-1, higher = more risky)
    reversibility = extract_reversibility(memory['content'])
    score += 0.2 * (1.0 - reversibility)
    
    # Stakeholder complexity (0-1)
    stakeholders = count_stakeholders(memory['content'])
    complexity = min(1.0, stakeholders / 5)  # 5+ = max complexity
    score += 0.15 * complexity
    
    # Unknown factors (0-1)
    unknowns = count_unknown_factors(memory['content'])
    unknown_score = min(1.0, unknowns / 3)  # 3+ = max unknowns
    score += 0.15 * unknown_score
    
    return min(1.0, score)  # Clamp to [0, 1]

def flag_high_risk_decisions() -> List[HighRiskDecision]:
    memories = memory_store.filter_by_type('decision')
    high_risk = []
    
    for memory in memories:
        score = risk_score(memory)
        
        if score > 0.7:  # 70% risk threshold
            high_risk.append({
                'memory': memory,
                'risk_score': score,
                'risk_factors': identify_risk_factors(memory),
                'mitigation': suggest_mitigation(memory, score)
            })
    
    return sorted(high_risk, key=lambda x: x['risk_score'], reverse=True)
```

### 2.4 API Endpoints

```python
# Endpoints for anomaly detection

@app.get("/anomalies")
async def list_anomalies():
    """List all detected anomalies"""
    return {
        'contradictions': find_contradictions(),
        'pattern_breaks': detect_pattern_breaks(),
        'high_risk_decisions': flag_high_risk_decisions(),
        'timestamp': datetime.now().isoformat()
    }

@app.get("/anomalies/contradictions")
async def get_contradictions():
    """List only contradictions"""
    return find_contradictions()

@app.get("/anomalies/pattern-breaks")
async def get_pattern_breaks():
    """List only pattern breaks"""
    return detect_pattern_breaks()

@app.get("/anomalies/high-risk")
async def get_high_risk():
    """List only high-risk decisions"""
    return flag_high_risk_decisions()

@app.post("/analyze/{memory_id}")
async def analyze_memory(memory_id: str):
    """Analyze single memory for anomalies"""
    memory = memory_store.get(memory_id)
    return {
        'memory': memory,
        'risk_score': risk_score(memory),
        'contradictions': find_contradictions_for_memory(memory_id),
        'pattern_impact': assess_pattern_impact(memory)
    }
```

---

## Part 3: Integration Strategy

### With Existing Phase 7 System

```
Phase 7: Semantic Search + ML Ranking
    ↓
Phase 10A: Summarization (uses memory store)
Phase 10B: Anomaly Detection (uses embeddings)
    ↓
API Endpoints
    ↓
User-facing Features
```

### Caching Strategy

```
Summary Cache:
- Daily: 7 days
- Weekly: 30 days
- Monthly: 90 days
- Custom: 7 days (or user specified)

Anomaly Cache:
- Contradictions: 24 hours (frequently updated)
- Pattern breaks: 12 hours (evolving)
- High-risk: 12 hours (changes with new memories)
```

### Performance Targets

| Operation | Target | Strategy |
|-----------|--------|----------|
| Daily recap | < 200ms | Cache frequently, warm on startup |
| Weekly summary | < 500ms | Compute async, cache aggressively |
| Monthly review | < 1s | Batch process, cache long-term |
| Find contradictions | < 500ms | Vector similarity optimized |
| Pattern detection | < 300ms | Baseline computed daily |
| Risk scoring | < 100ms | Per-memory scoring |

---

## Part 4: Quality Metrics

### Summarization Quality

```
Metrics:
- Coverage: % of memories included in summary
- Specificity: % of summary that's actionable
- Accuracy: % that matches user validation
- Freshness: Time since summary generated
- User rating: 1-5 scale feedback

Target:
- Coverage: > 80%
- Specificity: > 70%
- Accuracy: > 85%
- User rating: > 4.0
```

### Anomaly Detection Accuracy

```
Metrics:
- Precision: True positives / Total positives
- Recall: True positives / All real anomalies
- False positive rate: < 10%
- False negative rate: < 5%

Target:
- Precision: > 90%
- Recall: > 85%
- F1 Score: > 0.87
```

---

## Part 5: Testing Strategy

### Unit Tests

```python
# test_summarizer.py
- test_daily_recap_format()
- test_weekly_summary_trends()
- test_monthly_review_metrics()
- test_cache_persistence()
- test_empty_date_handling()

# test_anomaly_detector.py
- test_contradiction_detection()
- test_contradiction_scoring()
- test_pattern_break_detection()
- test_risk_scoring()
- test_high_risk_flagging()
```

### Integration Tests

```python
- test_summarization_with_real_memories()
- test_anomaly_detection_accuracy()
- test_api_endpoints_responding()
- test_caching_working()
- test_concurrent_requests()
```

### Acceptance Tests

```
- User receives daily recap
- User sees weekly trends
- System alerts on contradictions
- Risk decisions highlighted
- Performance under load (100 QPS)
```

---

## Summary

**Phase 10 delivers:**
- ✅ Daily recap generation
- ✅ Weekly trend analysis
- ✅ Monthly insights
- ✅ Contradiction detection
- ✅ Pattern break identification
- ✅ Risk scoring
- ✅ REST API endpoints (6 total)
- ✅ Comprehensive caching
- ✅ Quality metrics

**Ready for:** Phase 11 advanced features & Phase 8-10 integration
