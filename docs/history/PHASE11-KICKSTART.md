# Phase 11 Kickstart - Ready to Build

**Status:** Architecture + skeletons ready
**Timeline:** 2-3 sessions (4-5 hours) when Phase 8-10 complete
**Target:** Knowledge graph + NLP chat live

---

## Part A: Neo4j Schema Design

### Graph Model

```cypher
// Entity nodes
(:PERSON {
  id: "person_001",
  name: "John Doe",
  role: "Lead Engineer",
  influence_score: 0.85
})

(:PROJECT {
  id: "proj_001",
  name: "Mobile App Redesign",
  status: "active",
  start_date: "2026-08-01",
  owner: "person_001"
})

(:TECHNOLOGY {
  id: "tech_001",
  name: "React",
  category: "Framework",
  adoption_status: "adopted",
  confidence: 0.95
})

(:DECISION {
  id: "dec_001",
  title: "Use PostgreSQL for production",
  date_made: "2026-08-20",
  impact: "high",
  reversibility: "moderate",
  status: "active"
})

// Relationship types
(:PERSON)-[:LEADS]->(:PROJECT)
(:PERSON)-[:MAKES_DECISION]->(:DECISION)
(:DECISION)-[:USES]->(:TECHNOLOGY)
(:PROJECT)-[:DEPENDS_ON]->(:TECHNOLOGY)
(:DECISION)-[:CONTRADICTS]->(:DECISION)
(:DECISION)-[:IMPLEMENTS]->(:PROJECT)
```

### Neo4j Initialization

```python
# scripts/neo4j-init.py

from neo4j import GraphDatabase, BASIC_AUTH

class KnowledgeGraphDB:
    def __init__(self, uri="bolt://neo4j:7687", auth=("neo4j", "password")):
        self.driver = GraphDatabase.driver(uri, auth=auth)
        self.init_schema()
    
    def init_schema(self):
        """Initialize Neo4j schema"""
        with self.driver.session() as session:
            # Create constraints
            session.run("CREATE CONSTRAINT entity_id IF NOT EXISTS ON (e) ASSERT e.id IS UNIQUE")
            session.run("CREATE CONSTRAINT memory_id IF NOT EXISTS ON (m:Memory) ASSERT m.memory_id IS UNIQUE")
            
            # Create indexes
            session.run("CREATE INDEX person_name IF NOT EXISTS FOR (p:PERSON) ON (p.name)")
            session.run("CREATE INDEX project_status IF NOT EXISTS FOR (p:PROJECT) ON (p.status)")
            session.run("CREATE INDEX tech_adoption IF NOT EXISTS FOR (t:TECHNOLOGY) ON (t.adoption_status)")
            session.run("CREATE INDEX decision_impact IF NOT EXISTS FOR (d:DECISION) ON (d.impact)")
    
    def add_entity(self, entity_type: str, entity_data: dict):
        """Add entity to graph"""
        with self.driver.session() as session:
            query = f"""
            CREATE (e:{entity_type} {{
                id: $id,
                name: $name,
                properties: $properties,
                created_at: datetime()
            }})
            RETURN e
            """
            result = session.run(query, {
                'id': entity_data['id'],
                'name': entity_data['name'],
                'properties': entity_data.get('properties', {})
            })
            return result.single()
    
    def add_relationship(self, source_id: str, rel_type: str, target_id: str, props: dict = None):
        """Add relationship between entities"""
        with self.driver.session() as session:
            query = f"""
            MATCH (a {{id: $source}})
            MATCH (b {{id: $target}})
            CREATE (a)-[r:{rel_type} $props]->(b)
            RETURN r
            """
            result = session.run(query, {
                'source': source_id,
                'target': target_id,
                'props': props or {}
            })
            return result.single()
    
    def close(self):
        self.driver.close()
```

---

## Part B: Entity Extraction Pipeline

### Extraction Framework

```python
# scripts/entity-extractor.py

import spacy
import openai
from dataclasses import dataclass
from typing import List, Dict

@dataclass
class Entity:
    id: str
    type: str
    name: str
    description: str
    confidence: float
    properties: Dict

class EntityExtractor:
    def __init__(self):
        self.nlp = spacy.load("en_core_web_lg")
        self.memory_store = MemoryStore()
        self.graph = KnowledgeGraphDB()
    
    def extract_from_memory(self, memory: dict) -> List[Entity]:
        """Extract entities from single memory"""
        
        content = memory['content']
        memory_id = memory['memory_id']
        
        # Step 1: Run spaCy NER
        doc = self.nlp(content)
        spacy_entities = [
            (ent.text, ent.label_) for ent in doc.ents
        ]
        
        # Step 2: GPT-4 deep extraction
        prompt = f"""
        Extract entities from this memory:
        
        {content}
        
        For each entity, provide JSON:
        {{
          "name": "Entity Name",
          "type": "PERSON|PROJECT|TECHNOLOGY|DECISION",
          "description": "What this entity is",
          "confidence": 0.85,
          "properties": {{"key": "value"}}
        }}
        
        Return array of entities only, no other text.
        """
        
        response = openai.ChatCompletion.create(
            model="gpt-4-turbo-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2
        )
        
        gpt_entities = json.loads(response.choices[0].message.content)
        
        # Step 3: Create Entity objects
        entities = []
        for ent_data in gpt_entities:
            entity = Entity(
                id=f"entity_{hash(ent_data['name']) % 10000}",
                type=ent_data['type'],
                name=ent_data['name'],
                description=ent_data['description'],
                confidence=ent_data['confidence'],
                properties={
                    'source_memory': memory_id,
                    'extracted_date': datetime.now().isoformat(),
                    **ent_data.get('properties', {})
                }
            )
            entities.append(entity)
            
            # Add to graph
            self.graph.add_entity(entity.type, {
                'id': entity.id,
                'name': entity.name,
                'properties': entity.properties
            })
        
        return entities
    
    def extract_relationships(self, memory: dict, entities: List[Entity]):
        """Extract relationships between entities"""
        
        content = memory['content']
        
        # For each pair of entities
        for i, ent1 in enumerate(entities):
            for ent2 in entities[i+1:]:
                # Check if they're related
                rel_type = self.detect_relationship(content, ent1, ent2)
                
                if rel_type:
                    self.graph.add_relationship(
                        ent1.id,
                        rel_type,
                        ent2.id,
                        {'source_memory': memory['memory_id']}
                    )
    
    def detect_relationship(self, content: str, ent1: Entity, ent2: Entity) -> str:
        """Detect if entities are related and how"""
        
        prompt = f"""
        Are these entities related in this text?
        
        Text: {content}
        Entity 1: {ent1.name} ({ent1.type})
        Entity 2: {ent2.name} ({ent2.type})
        
        If related, return ONE relationship type from this list:
        - MENTIONS (A mentions B)
        - USES (A uses B)
        - DEPENDS_ON (A depends on B)
        - CONTRADICTS (A contradicts B)
        - IMPLEMENTS (A implements B)
        - LEADS (A leads B)
        - CREATES (A creates B)
        
        If not related, return "NONE"
        
        Return only the relationship type, nothing else.
        """
        
        response = openai.ChatCompletion.create(
            model="gpt-4-turbo-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1
        )
        
        rel_type = response.choices[0].message.content.strip()
        return rel_type if rel_type != "NONE" else None

# Usage
if __name__ == "__main__":
    extractor = EntityExtractor()
    
    # Get all memories
    memories = MemoryStore().get_all_active()
    
    for memory in memories:
        print(f"Extracting from {memory['memory_id']}...")
        entities = extractor.extract_from_memory(memory)
        extractor.extract_relationships(memory, entities)
    
    print("✓ Graph populated with entities and relationships")
    extractor.graph.close()
```

---

## Part C: Chat Framework Skeleton

### Intent Classifier

```python
# scripts/chat-interface.py

from enum import Enum
import re

class Intent(Enum):
    QUERY = "Query for information"
    SUMMARIZE = "Get summary/recap"
    ANOMALY = "Check for issues"
    CREATE = "Add new memory"
    ANALYZE = "Deep analysis"
    REFLECT = "Self-reflection"
    GRAPH = "Graph query"

class IntentClassifier:
    def __init__(self):
        self.patterns = {
            Intent.SUMMARIZE: r"(summarize|recap|what happened|summary|daily|weekly|monthly)",
            Intent.ANOMALY: r"(anomaly|contradiction|risk|alert|problem|wrong|issue)",
            Intent.CREATE: r"(remember|note|learned|decided|remember to)",
            Intent.ANALYZE: r"(analyze|deep dive|why|how|explain|what does)",
            Intent.GRAPH: r"(connected|relationship|depends|who|what's|affects)",
            Intent.REFLECT: r"(reflect|think|consider|thoughts|feeling)",
        }
    
    def classify(self, user_input: str) -> Intent:
        """Classify user message intent"""
        
        # Pattern matching first (fast path)
        for intent, pattern in self.patterns.items():
            if re.search(pattern, user_input.lower()):
                return intent
        
        # Default to query
        return Intent.QUERY

class ConversationContext:
    def __init__(self, max_turns=5):
        self.history = []
        self.max_turns = max_turns
        self.entities_mentioned = set()
    
    def add_message(self, role: str, content: str):
        """Add to conversation history"""
        self.history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        
        # Keep last N turns
        if len(self.history) > self.max_turns * 2:
            self.history = self.history[-self.max_turns*2:]
    
    def get_context_prompt(self) -> str:
        """Build context for LLM"""
        prompt = "Previous conversation:\n"
        for msg in self.history[-4:]:  # Last 2 turns
            prompt += f"{msg['role']}: {msg['content']}\n"
        return prompt

class ChatAgent:
    def __init__(self):
        self.intent_classifier = IntentClassifier()
        self.hybrid_search = HybridSearchEngine()
        self.graph = KnowledgeGraphDB()
        self.conversations = {}  # conv_id -> ConversationContext
    
    def chat(self, user_input: str, conversation_id: str = None) -> Dict:
        """Process user message"""
        
        # Get or create conversation
        if not conversation_id:
            conversation_id = str(uuid.uuid4())
        
        if conversation_id not in self.conversations:
            self.conversations[conversation_id] = ConversationContext()
        
        context = self.conversations[conversation_id]
        context.add_message("user", user_input)
        
        # Classify intent
        intent = self.intent_classifier.classify(user_input)
        
        # Route to handler
        handlers = {
            Intent.QUERY: self.handle_query,
            Intent.SUMMARIZE: self.handle_summarize,
            Intent.ANOMALY: self.handle_anomaly,
            Intent.CREATE: self.handle_create,
            Intent.ANALYZE: self.handle_analyze,
            Intent.GRAPH: self.handle_graph_query,
            Intent.REFLECT: self.handle_reflect,
        }
        
        handler = handlers.get(intent, self.handle_query)
        response_text = handler(user_input, context)
        
        # Add response to context
        context.add_message("assistant", response_text)
        
        return {
            "response": response_text,
            "conversation_id": conversation_id,
            "intent": intent.name,
            "follow_ups": self.generate_follow_ups(intent)
        }
    
    def handle_query(self, query: str, context: ConversationContext) -> str:
        """Handle information query"""
        
        # Search for relevant memories
        results = self.hybrid_search.search(query, top_k=3)
        
        if not results:
            return "I don't have information about that in my memory."
        
        # Build response with citations
        response = "Based on my memories:\n\n"
        for i, result in enumerate(results, 1):
            response += f"{i}. {result['content']}\n"
            response += f"   [Confidence: {result.get('confidence', 0.5)}]\n\n"
        
        return response
    
    def handle_summarize(self, query: str, context: ConversationContext) -> str:
        """Handle summarization requests"""
        
        # Extract date if provided
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", query)
        date = date_match.group(1) if date_match else datetime.now().strftime("%Y-%m-%d")
        
        # Check what type of summary
        if "weekly" in query.lower():
            summary_type = "weekly"
        elif "monthly" in query.lower():
            summary_type = "monthly"
        else:
            summary_type = "daily"
        
        # API call to get summary
        # (this will be real when Phase 10 complete)
        return f"📋 {summary_type.title()} summary for {date}..."
    
    def handle_anomaly(self, query: str, context: ConversationContext) -> str:
        """Handle anomaly detection queries"""
        
        # Check for contradictions
        # API call to get anomalies
        return "🚨 Checking for contradictions and risks..."
    
    def handle_create(self, query: str, context: ConversationContext) -> str:
        """Handle memory creation"""
        
        # Extract memory content from query
        return f"💾 I'll remember: {query}"
    
    def handle_analyze(self, query: str, context: ConversationContext) -> str:
        """Handle deep analysis"""
        
        # Extract entities from query
        # Use graph to analyze
        return f"🔍 Analyzing {query}..."
    
    def handle_graph_query(self, query: str, context: ConversationContext) -> str:
        """Handle graph traversal queries"""
        
        # Parse graph query intent
        if "connected" in query.lower():
            return "Finding connections in your knowledge graph..."
        elif "depends" in query.lower():
            return "Analyzing dependencies..."
        else:
            return "Exploring relationships..."
    
    def handle_reflect(self, query: str, context: ConversationContext) -> str:
        """Handle reflection requests"""
        
        return "Let me help you reflect on that..."
    
    def generate_follow_ups(self, intent: Intent) -> List[str]:
        """Suggest follow-up questions"""
        
        follow_ups = {
            Intent.QUERY: [
                "Would you like more details?",
                "Does this match your recollection?",
                "Should I search for something else?"
            ],
            Intent.SUMMARIZE: [
                "Would you like insights for a different period?",
                "Should I focus on a specific category?",
                "Want to compare with last week?"
            ],
            Intent.ANOMALY: [
                "Should I drill into any of these?",
                "Want to explore the contradictions?",
                "How should we address these risks?"
            ],
        }
        
        return follow_ups.get(intent, [])
```

### REST API Endpoints

```python
@app.post("/chat")
async def chat(message: str, conversation_id: str = None):
    """Chat with AI about your memories"""
    
    agent = ChatAgent()
    result = agent.chat(message, conversation_id)
    
    return result

@app.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str):
    """Get conversation history"""
    
    agent = ChatAgent()
    context = agent.conversations.get(conversation_id)
    
    if not context:
        return {"error": "Conversation not found"}
    
    return {"history": context.history}
```

---

## Part D: Implementation Checklist

### Session 1: Entity Extraction
- [ ] Set up Neo4j Docker container
- [ ] Create database schema + indexes + constraints
- [ ] Implement EntityExtractor class
- [ ] spaCy + GPT-4 hybrid extraction
- [ ] Relationship detection
- [ ] Test entity extraction (10+ test cases)
- [ ] Run against all 46+ memories
- [ ] Verify graph population

**Output:** 100+ entities, 200+ relationships in Neo4j

### Session 2: Chat Interface
- [ ] Implement IntentClassifier
- [ ] Create ChatAgent skeleton
- [ ] Implement handlers for each intent
- [ ] Add ConversationContext
- [ ] Create API endpoints
- [ ] Test intent classification (20+ cases)
- [ ] Test each handler
- [ ] Integration tests

**Output:** Chat interface responding to 6 intent types

### Session 3: Graph Queries + Integration
- [ ] Cypher queries for common patterns
- [ ] Graph visualization endpoints
- [ ] Integration with Phase 7 search
- [ ] Performance optimization
- [ ] E2E chat workflows
- [ ] Documentation
- [ ] Final integration tests

**Output:** Full knowledge graph + chat system working

---

## Summary

**Phase 11 Kickstart provides:**
- ✅ Neo4j schema design
- ✅ Entity extraction pipeline skeleton
- ✅ Chat interface framework
- ✅ Implementation checklist
- ✅ Ready to code immediately

**Timeline:** 2-3 sessions (4-5 hours)
**Deliverable:** Knowledge graph + NLP chat live

**Status:** 🚀 Ready to build Phase 11!
