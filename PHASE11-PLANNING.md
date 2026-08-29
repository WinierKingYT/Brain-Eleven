# Phase 11: Advanced Features - Planning & Architecture

**Status:** 🚀 Future phase planning
**Target:** 2-3 weeks after Phase 8-10 complete
**Complexity:** Very High
**Scope:** Choose 2-3 of 5 advanced features

---

## Decision Framework: Which Features?

### Option A: Maximum User Impact
**Features:** Auto-Summarization (Phase 10) ✅ + Anomaly Detection (Phase 10) ✅
- **Why:** Direct user value, smart reminders, risk alerts
- **Timeline:** Now (Phase 10)
- **Impact:** High

### Option B: Deep Knowledge Integration
**Features:** Knowledge Graph + NLP Chat Interface
- **Why:** Understand relationships, conversational access
- **Timeline:** 2-3 weeks (Phase 11)
- **Impact:** Very High (long-term)

### Option C: Enterprise Features
**Features:** Multi-user Collaboration + Advanced Analytics
- **Why:** Team capabilities, insights
- **Timeline:** 3-4 weeks
- **Impact:** High (team level)

### Recommendation: A + B
Start with Phase 10 (summarization + anomaly), then Phase 11 = Knowledge Graph + NLP

---

## Phase 11 Option 1: Knowledge Graph Integration

### Architecture

```
Memory Store (46+ memories with embeddings)
    ↓
Entity Extraction
├─ People: Names, roles, relationships
├─ Projects: Names, status, teams
├─ Technologies: Tools, frameworks, platforms
└─ Decisions: Impact, reversibility, status
    ↓
Relationship Discovery
├─ mentions (A mentions B)
├─ depends-on (A requires B)
├─ contradicts (A vs B)
├─ implements (A implements B)
└─ references (A references B)
    ↓
Neo4j Database
    ↓
Query & Analysis
├─ Shortest path (how X connects to Z?)
├─ Impact analysis (what breaks if X changes?)
├─ Timeline (evolution of decisions)
└─ Influence maps (who influences what?)
```

### 11.1 Entity Extraction

**Goal:** Extract structured entities from unstructured memory text

**Entities to Extract:**

```python
@dataclass
class Entity:
    id: str  # Unique entity ID
    type: EntityType  # PERSON, PROJECT, TECHNOLOGY, DECISION
    name: str
    description: str
    confidence: float  # Extraction confidence
    mentions: List[str]  # Memory IDs that mention this entity
    properties: Dict  # Type-specific properties

class PERSON(Entity):
    role: str
    responsibilities: List[str]
    relationships: List[str]
    influence_score: float

class PROJECT(Entity):
    status: str  # Active, completed, planned
    owner: str
    team_members: List[str]
    timeline: Dict  # start_date, end_date, milestones
    dependencies: List[str]

class TECHNOLOGY(Entity):
    category: str  # Database, Framework, Tool, Language
    adoption_status: str  # Evaluating, Adopted, Deprecated
    use_cases: List[str]
    alternatives: List[str]

class DECISION(Entity):
    date_made: str
    impact_level: str  # Low, Medium, High
    reversibility: str  # Easy, Moderate, Hard
    status: str  # Active, Revisited, Deprecated
    rationale: str
```

**Implementation:**

```python
class EntityExtractor:
    def __init__(self, model="gpt-4-turbo-mini"):
        self.model = model
        self.nlp = spacy.load("en_core_web_lg")
        
    def extract_entities(self, memory: Memory) -> List[Entity]:
        """Extract entities from memory text"""
        
        # 1. Use spaCy for base NER
        doc = self.nlp(memory['content'])
        spacy_entities = [
            (ent.text, ent.label_) for ent in doc.ents
        ]
        
        # 2. Use GPT-4 for deeper extraction
        prompt = f"""
        Extract entities from this memory:
        
        {memory['content']}
        
        For each entity, provide:
        - Name
        - Type (PERSON, PROJECT, TECHNOLOGY, DECISION)
        - Description
        - Relationships to other entities
        - Confidence (0-1)
        
        Output as JSON array.
        """
        
        response = openai.ChatCompletion.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2  # Low temp for consistent extraction
        )
        
        gpt_entities = json.loads(response.choices[0].message.content)
        
        # 3. Merge and deduplicate
        merged = merge_entity_lists(spacy_entities, gpt_entities)
        
        # 4. Store in knowledge graph
        entities = []
        for ent_data in merged:
            entity = create_entity(ent_data)
            self.graph.add_node(entity)
            entities.append(entity)
        
        return entities
    
    def extract_relationships(self, memory: Memory, entities: List[Entity]) -> List[Relationship]:
        """Extract relationships between entities"""
        
        relationships = []
        
        for i, ent1 in enumerate(entities):
            for ent2 in entities[i+1:]:
                # Check if entities related in text
                rel_type = detect_relationship(
                    memory['content'], ent1, ent2
                )
                
                if rel_type:
                    rel = Relationship(
                        source=ent1.id,
                        target=ent2.id,
                        type=rel_type,
                        source_memory=memory['memory_id'],
                        confidence=0.85
                    )
                    relationships.append(rel)
                    self.graph.add_edge(ent1.id, ent2.id, relation=rel_type)
        
        return relationships
```

### 11.2 Neo4j Integration

**Setup:**

```yaml
# docker-compose.yml additions
neo4j:
  image: neo4j:5.15
  environment:
    NEO4J_AUTH: neo4j/password
    NEO4J_ACCEPT_LICENSE_AGREEMENT: "yes"
  ports:
    - "7687:7687"  # Bolt protocol
    - "7474:7474"  # Web interface
  volumes:
    - neo4j-data:/data

# Python driver
from neo4j import GraphDatabase

class KnowledgeGraph:
    def __init__(self, uri="bolt://neo4j:7687", auth=("neo4j", "password")):
        self.driver = GraphDatabase.driver(uri, auth=auth)
    
    def add_entity(self, entity: Entity):
        """Add entity to graph"""
        with self.driver.session() as session:
            session.run(f"""
                CREATE (n:{entity.type} {{
                    id: $id,
                    name: $name,
                    description: $description,
                    confidence: $confidence
                }})
            """, {
                'id': entity.id,
                'name': entity.name,
                'description': entity.description,
                'confidence': entity.confidence
            })
    
    def add_relationship(self, source_id: str, target_id: str, rel_type: str):
        """Add relationship between entities"""
        with self.driver.session() as session:
            session.run(f"""
                MATCH (a {{id: $source}})
                MATCH (b {{id: $target}})
                CREATE (a)-[:{rel_type}]->(b)
            """, {'source': source_id, 'target': target_id})
```

### 11.3 Knowledge Graph Queries

**Common Queries:**

```cypher
# Find shortest path from X to Z
MATCH path = shortestPath(
    (a {name: "X"})-[*]-(b {name: "Z"})
)
RETURN path

# What depends on this technology?
MATCH (tech {name: "PostgreSQL"}) <-[r:USES]- (proj)
RETURN proj.name, proj.status

# Who influences this decision?
MATCH (decision {type: "Decision"})
      -[:INFLUENCED_BY]-> (person)
RETURN person.name, count(*) as influence_score
ORDER BY influence_score DESC

# Decision timeline
MATCH (d:Decision)
RETURN d.name, d.date_made, d.impact_level
ORDER BY d.date_made

# Impact analysis: what breaks if X is removed?
MATCH (entity {name: "X"})
      -[r:DEPENDS_ON]-> (dependent)
RETURN dependent, r.impact_level
```

### 11.4 Visualization

```python
# Neo4j Browser built-in at http://localhost:7474
# Custom REST API for programmatic access

@app.get("/graph/entity/{entity_id}")
async def get_entity(entity_id: str):
    """Get entity and its connections"""
    return query_graph(f"""
        MATCH (e {{id: $id}})
        OPTIONAL MATCH (e)-[r]->(connected)
        RETURN e, r, connected
    """, {'id': entity_id})

@app.get("/graph/path")
async def find_path(source: str, target: str):
    """Find shortest path between entities"""
    return query_graph(f"""
        MATCH path = shortestPath((a {{name: $source}})-[*]-(b {{name: $target}}))
        RETURN path
    """, {'source': source, 'target': target})

@app.get("/graph/impact/{entity_id}")
async def analyze_impact(entity_id: str):
    """Analyze impact of entity changes"""
    return query_graph(f"""
        MATCH (e {{id: $id}})-[r:DEPENDS_ON]->(dep)
        RETURN dep, r.impact_level
    """, {'id': entity_id})
```

---

## Phase 11 Option 2: NLP Chat Interface

### Architecture

```
User Input (Natural Language)
    ↓
Intent Classification
├─ Query (asking for info)
├─ Summarize (get recap)
├─ Alert (check anomalies)
├─ Create (add memory)
└─ Analyze (deep dive)
    ↓
Context Retrieval
├─ Get relevant memories
├─ Search with hybrid search
├─ Retrieve from knowledge graph
└─ Gather context
    ↓
Response Generation (GPT-4)
├─ Direct answer
├─ With citations
├─ With recommendations
└─ With follow-ups
    ↓
User Output
```

### 11.5 Intent Classification

```python
from enum import Enum

class Intent(Enum):
    QUERY = "Query for information"
    SUMMARIZE = "Get summary/recap"
    ANOMALY = "Check for issues"
    CREATE = "Add new memory"
    ANALYZE = "Deep analysis"
    REFLECT = "Self-reflection"

class ChatInterface:
    def __init__(self):
        self.intent_classifier = IntentClassifier()
        self.hybrid_search = HybridSearchEngine()
        self.knowledge_graph = KnowledgeGraph()
    
    def classify_intent(self, user_input: str) -> Intent:
        """Classify user message intent"""
        
        # First, try pattern matching
        patterns = {
            Intent.SUMMARIZE: r"(summarize|recap|what happened|summary)",
            Intent.ANOMALY: r"(anomaly|contradiction|risk|alert|problem)",
            Intent.CREATE: r"(remember|note|remember to|learned that)",
            Intent.ANALYZE: r"(analyze|deep dive|why|how)",
        }
        
        for intent, pattern in patterns.items():
            if re.search(pattern, user_input.lower()):
                return intent
        
        # If no pattern match, use GPT classification
        prompt = f"""
        Classify the user's intent:
        "{user_input}"
        
        Options: {[e.name for e in Intent]}
        
        Return just the intent name.
        """
        
        response = openai.ChatCompletion.create(
            model="gpt-4-turbo-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        
        return Intent[response.choices[0].message.content.strip()]

class ConversationalAgent:
    def chat(self, user_message: str, conversation_history: List[str] = None) -> str:
        """Process user message and generate response"""
        
        if conversation_history is None:
            conversation_history = []
        
        # 1. Classify intent
        intent = self.classify_intent(user_message)
        
        # 2. Retrieve relevant context
        context = self.retrieve_context(user_message, intent)
        
        # 3. Generate response
        response = self.generate_response(
            user_message, 
            intent, 
            context, 
            conversation_history
        )
        
        # 4. Add citations
        response_with_citations = self.add_citations(response, context)
        
        # 5. Store interaction (for learning)
        self.store_interaction(user_message, response, intent)
        
        return response_with_citations
    
    def retrieve_context(self, query: str, intent: Intent) -> Dict:
        """Get relevant memories and knowledge"""
        
        context = {}
        
        # Hybrid search for similar memories
        search_results = self.hybrid_search.search(query, top_k=5)
        context['relevant_memories'] = search_results
        
        # Entity/relationship search if anomaly
        if intent == Intent.ANOMALY:
            context['contradictions'] = find_contradictions()
            context['high_risk'] = flag_high_risk_decisions()
        
        # Knowledge graph traversal if analyze
        if intent == Intent.ANALYZE:
            entities = extract_entities_from_query(query)
            context['entity_graph'] = traverse_graph(entities)
        
        return context
    
    def generate_response(self, query: str, intent: Intent, context: Dict, history: List[str]) -> str:
        """Generate response with GPT-4"""
        
        # Build messages including context
        messages = [
            {"role": "system", "content": self.build_system_prompt(intent)},
            *[{"role": "user", "content": msg} for msg in history[-4:]],  # Last 4 turns
            {"role": "user", "content": self.build_context_prompt(query, context)},
        ]
        
        response = openai.ChatCompletion.create(
            model="gpt-4-turbo-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=500
        )
        
        return response.choices[0].message.content
    
    def add_citations(self, response: str, context: Dict) -> str:
        """Add source citations to response"""
        
        cited_response = response
        
        for i, memory in enumerate(context.get('relevant_memories', [])[:3]):
            memory_ref = f"[Source {i+1}: {memory['memory_id'][:8]}...]"
            cited_response += f"\n{memory_ref}"
        
        return cited_response
```

### 11.6 Chat API Endpoints

```python
@app.post("/chat")
async def chat(message: str, conversation_id: str = None):
    """Chat with the AI about your memories"""
    
    # Load conversation history
    history = load_history(conversation_id) if conversation_id else []
    
    # Process message
    response = agent.chat(message, history)
    
    # Save conversation
    conversation_id = save_conversation(history + [message, response])
    
    return {
        'response': response,
        'conversation_id': conversation_id,
        'intent': classify_intent(message).name,
        'citations': extract_citations(response)
    }

@app.get("/chat/conversations")
async def list_conversations():
    """List all conversations"""
    return get_all_conversations()

@app.get("/chat/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get conversation history"""
    return load_conversation(conversation_id)

@app.delete("/chat/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete conversation"""
    return delete_conversation_history(conversation_id)
```

### 11.7 Example Conversations

```
User: "What was I thinking about databases last week?"

Response: "Based on your memories, you made several database-related decisions:

1. Decided PostgreSQL is the best choice for production (2026-08-20)
   - Confidence: 95%
   - Impact: High
   
2. Evaluated database alternatives (2026-08-25)
   - Considered MongoDB as alternative
   - Decided PostgreSQL still best
   
3. Security concerns raised (2026-08-28)
   - Need to review authentication approach
   - Related to user data protection

Would you like to dive deeper into any of these?"

---

User: "What contradicts my recent thinking?"

Response: "I found 2 potential contradictions:

1. Database strategy shift:
   - Aug 20: PostgreSQL is the best choice
   - Aug 28: Considering alternatives
   
   Contradiction Score: 0.92 (high)
   
   Suggestion: Review why PostgreSQL preference changed and document new thinking.

2. API design approach:
   - Earlier: REST API is best practice
   - Recent: Considering GraphQL
   
   Contradiction Score: 0.78 (moderate)
   
   What's driving these shifts?"

---

User: "What should I focus on next?"

Response: "Based on your open loops and risk analysis:

🔴 High Priority:
- Implement authentication (flagged as high-risk on 2026-08-28)
  Reasoning: High impact, but still unresolved

🟡 Medium Priority:
- Revisit microservices decision (flagged pattern break)
  Reasoning: You've shifted thinking 3 times in 2 weeks

🟢 Low Priority:
- Update testing strategy (low-risk, progressing)

Recommendation: Start with authentication - it's both high-risk and time-sensitive."
```

---

## Phase 11: Timeline & Effort

| Feature | Sessions | Complexity | Impact | Lines |
|---------|----------|-----------|---------|--------|
| **Knowledge Graph** | 2-3 | Very High | High | 1,200-1,500 |
| **NLP Chat** | 2-3 | High | Very High | 1,000-1,200 |
| **Combined Phase 11** | 4-5 | Very High | Very High | 2,200-2,700 |

### Session Breakdown

**Session 1 (Phase 11 Start):**
- Entity extraction implementation (300 LOC)
- Neo4j integration (200 LOC)
- Basic queries (100 LOC)
- Tests (150 LOC)

**Session 2:**
- NLP chat interface (400 LOC)
- Intent classification (200 LOC)
- Context retrieval (200 LOC)
- Tests (150 LOC)

**Session 3:**
- Knowledge graph queries (300 LOC)
- Visualization API (200 LOC)
- Conversation history (150 LOC)
- Integration tests (200 LOC)

**Session 4 (Optional):**
- Advanced queries (200 LOC)
- Performance optimization (100 LOC)
- Documentation (150 LOC)

---

## Phase 11: Success Criteria

```
Knowledge Graph:
  ✅ 100+ entities extracted
  ✅ Relationships identified
  ✅ Graph queries working
  ✅ Shortest path working
  ✅ Impact analysis working

NLP Chat:
  ✅ Intent classification > 90% accurate
  ✅ Response quality > 4.0/5.0
  ✅ Citations accurate
  ✅ Conversation history persistent
  ✅ Multi-turn context working

Combined:
  ✅ < 1s query latency
  ✅ Graph + chat integrated
  ✅ Full documentation
  ✅ E2E tests passing
  ✅ Production ready
```

---

## Go/No-Go Timeline

```
Phase 8-10 complete:
  September 2026 (target)
  ↓
Phase 11 Start:
  Decision point - do we proceed?
  ↓
Phase 11 Complete:
  Mid-September 2026
  ↓
Production Launch 🚀:
  Late September 2026
```

---

**Next Step:** Complete Phases 8-10, then decide on Phase 11 scope based on user feedback
