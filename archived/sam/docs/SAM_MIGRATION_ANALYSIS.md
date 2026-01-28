# 🔄 SAM Migration Analysis: Current Implementation → Spreading Activation Memory

**Purpose**: Compare the current CosmosDB-tied implementation with the new SAM (Spreading Activation Memory) architecture, identify reusable components, and recommend an implementation plan.

**Date**: January 19, 2026

---

## 1. Executive Summary

### Current State
The existing implementation is a **CosmosDB-specific memory service** with:
- Tight coupling to Azure CosmosDB for storage
- Service-based architecture (FastAPI server + HTTP client)
- In-memory session buffer for unstructured conversation turns
- Reflection process for insight extraction
- Two deployment modes: Remote (server) and Embedded

### Target State (SAM)
SAM defines a **cognitive-inspired memory architecture** with:
- Database abstraction layer (SQLite default, Postgres, Cosmos DB)
- 5-node ontology: Episode → Entity → Claim → Insight → Procedure
- Spreading activation retrieval algorithm
- Decay/forgetting mechanisms
- Framework-agnostic design (support LangGraph, Microsoft Agent Framework, etc.)

### Key Decisions
1. **KEEP**: Service-based architecture, in-memory turn buffer
2. **ELIMINATE**: Embedded provider mode (for framework independence)
3. **ADD**: Database abstraction layer (MemoryStore interface)
4. **REFACTOR**: Data model from flat documents to graph ontology
5. **REFACTOR**: Retrieval from vector search to spreading activation

---

## 2. Detailed Comparison

### 2.1 Data Model Comparison

**Key Concept Clarification: Episode**

An **Episode** in SAM is essentially a chat session that accumulates content from multiple turns:
- Working memory buffer holds active turns (unstructured, in-memory)
- When buffer is flushed (every k turns), content is **appended** to the current open Episode
- A new Episode starts when the current one exceeds a size limit (default: **10,000 tokens**)
- This replaces both "session" and "interaction" concepts from the current implementation

| Current Implementation | SAM Architecture | Migration Impact |
|----------------------|------------------|------------------|
| **InteractionDocument** (multi-turn chunks) | **Episode** node (accumulates flushed turns) | ✅ Similar concept, Episode is larger |
| **SessionSummaryDocument** | Episode metadata (summary, key_topics) | ✅ Merged into Episode |
| `session_id` everywhere | Episode.id (one open Episode at a time) | ✅ Simplified |
| `content` + `summary` text fields | Episode has `raw_content` + `summary` | ✅ Direct mapping |
| `content_vector` + `summary_vector` | Single `embedding` per Episode | Simplify |
| **SessionInsightDocument** | **Claim** or **Insight** depending on content | ⚠️ Split: descriptive vs prescriptive |
| `insight_type: "session"` | Claim (entity-bound, descriptive) | Need entity extraction |
| `insight_type: "long_term"` | Insight (generalized, prescriptive) | Rename and restructure |
| No Entity concept | **Entity** node type (users, accounts, concepts) | 🆕 New capability |
| No Procedure concept | **Procedure** node type | 🆕 New capability |
| Implicit relationships (user_id, session_id) | Explicit typed edges (ABOUT, SUPPORTS, etc.) | ⚠️ Major restructure |

### 2.2 Storage Layer Comparison

| Current Implementation | SAM Architecture | Gap |
|----------------------|------------------|-----|
| CosmosDB-only | SQLite (default) + Postgres + CosmosDB | 🔴 Need abstraction layer |
| Container-per-type (`interactions`, `insights`, `summaries`) | Table-per-type (`episodes`, `entities`, `claims`, `edges`) | Schema migration |
| `session_summaries` container | Eliminated (merged into Episode) | ✅ Simplified |
| Cosmos vector search API | sqlite-vec / pgvector / Cosmos vector | 🔴 Need unified interface |
| Cosmos full-text search | FTS5 / tsvector / Cosmos FTS | 🔴 Need unified interface |
| No graph traversal | Spreading activation algorithm | 🔴 New implementation |
| JSON documents | Relational + JSON hybrid | Schema migration |

### 2.3 Retrieval Comparison

| Current (CFR Agent) | SAM (Spreading Activation) | Gap |
|--------------------|---------------------------|-----|
| Mini-agent with 3 search tools | Algorithm-based retrieval | Different paradigm |
| Vector similarity search | Anchor → Spread → Filter → Synthesize | 🔴 New algorithm |
| Agent decides search strategy | Goal-directed activation propagation | Different approach |
| Returns raw search results | Returns subgraph with reasoning chain | Richer output |
| No decay consideration | Temporal decay affects retrieval | 🆕 New feature |
| No degree penalty | Hub damping (degree penalty) | 🆕 New feature |

### 2.4 Service Architecture Comparison

| Current Implementation | SAM Architecture | Alignment |
|----------------------|------------------|-----------|
| FastAPI server (`server/main.py`) | Service-based (to keep) | ✅ Aligned |
| HTTP client (`CosmosMemoryProvider`) | HTTP client adapter | ✅ Aligned |
| Session pool (`SessionPool`) | Session management (compatible) | ✅ Aligned |
| In-memory turn buffer (`CurrentMemoryKeeper`) | Working memory (to keep) | ✅ Aligned |
| Background eviction | TTL + LRU eviction | ✅ Aligned |

### 2.5 Framework Integration Comparison

| Current Implementation | SAM Architecture | Alignment |
|----------------------|------------------|-----------|
| Microsoft Agent Framework ContextProvider | Framework-agnostic API | ⚠️ Need abstraction |
| Embedded mode (`cosmos_memory_provider_embedded.py`) | Eliminate | ✅ Simplifies |
| Remote mode (`cosmos_memory_provider.py`) | HTTP client pattern | ✅ Keep pattern |
| Tool injection (`recall_facts`) | API-based retrieval | ✅ Compatible |

---

## 3. Components to KEEP (Reusable)

### 3.1 Service Architecture ✅
**Files**: `server/main.py`, `memory/session_pool.py`

The FastAPI server architecture is exactly what SAM needs:
- RESTful endpoints for memory operations
- Session pooling with LRU eviction
- Shared resource management (DB clients, LLM clients)
- Background task handling (eviction, reflection)

**Reuse Strategy**: Keep server structure, swap out storage layer.

```python
# Current: server/main.py
@app.post("/sessions/start")
async def start_session(request: SessionStartRequest):
    session = await session_pool.get_or_create(...)
    return session.orchestrator.get_context()

# SAM: Same pattern, different orchestrator
@app.post("/sessions/start")
async def start_session(request: SessionStartRequest):
    session = await session_pool.get_or_create(...)
    return session.memory_graph.get_context()  # New SAM interface
```

### 3.2 In-Memory Turn Buffer ✅
**Files**: `memory/current_memory_keeper.py`

The turn buffer design is excellent:
- k-turn accumulation before processing
- Cumulative summary updates
- Active turn window for context

**Reuse Strategy**: Keep the buffer logic, change what happens on prune.

```python
# Current: Creates InteractionDocument in CosmosDB
async def maybe_prune(self) -> Optional[Dict]:
    if len(self.turn_buffer) < self.config.K_TURN_BUFFER:
        return None
    # ... generate metadata, store to CosmosDB

# SAM: Append flushed turns to current open Episode
async def maybe_prune(self) -> Optional[Dict]:
    if len(self.turn_buffer) < self.config.K_TURN_BUFFER:
        return None
    
    # Get or create current open Episode
    episode = await self._get_or_create_open_episode()
    
    # Append flushed turns to Episode
    flushed_content = self._format_turns(self.turn_buffer[:self.config.K_TURN_BUFFER])
    await self.memory_store.append_to_episode(episode.id, flushed_content)
    
    # Check if Episode exceeds size limit (default 10k tokens)
    if episode.token_count > self.config.MAX_EPISODE_TOKENS:
        await self._close_episode(episode.id)
        # Next flush will create new Episode
    
    # Extract entities/claims from flushed content
    entities, claims = await self._extract_entities_claims(flushed_content, episode.id)
    await self.memory_store.store_extractions(entities, claims)
```

### 3.3 Reflection Process ✅ (Partial)
**Files**: `memory/reflection.py`

The reflection architecture is sound:
- Episode-close analysis (triggered when Episode exceeds size limit)
- Long-term synthesis
- Structured LLM outputs

**Reuse Strategy**: Keep structure, change output types and triggers.

```python
# Current: Produces SessionInsightDocument
class SessionInsight(BaseModel):
    insight_text: str
    category: str
    confidence: float
    importance: str

# SAM: Produces Claims and Insights separately
class ExtractionResult(BaseModel):
    claims: List[ClaimExtraction]      # Descriptive, entity-bound
    insights: List[InsightExtraction]  # Prescriptive, generalized
    entities: List[EntityExtraction]   # New!
```

### 3.4 Provider Configuration ✅
**Files**: `memory/provider_config.py`, `memory/config.py`

Configuration structure is reusable:
- Feature flags (include_insights, include_summaries)
- Buffer sizes (k-turn, active-turns)
- Model configurations

**Reuse Strategy**: Extend for SAM-specific settings.

```python
# SAM extensions
class SAMConfig(MemoryConfig):
    # Episode management
    MAX_EPISODE_TOKENS: int = 10_000  # Start new Episode when exceeded
    
    # Spreading activation parameters
    activation_threshold: float = 0.1
    max_hops: int = 3
    degree_penalty_base: float = 5.0
    
    # Storage engine
    storage_engine: Literal["sqlite", "postgres", "cosmos"] = "sqlite"
    database_url: str = "sqlite:///memory.db"
```

---

## 4. Components to ELIMINATE

### 4.1 Embedded Provider Mode ❌
**Files**: `memory/cosmos_memory_provider_embedded.py`, `memory/cosmos_agent_memory.py`

**Reason**: Creates tight coupling to Microsoft Agent Framework

**Current Problem**:
```python
# Embedded mode tightly couples to ContextProvider interface
class CosmosMemoryProvider(ContextProvider):  # MS Agent Framework specific
    async def invoking(self, messages: ChatMessage, **kwargs) -> Context:
        ...
    async def invoked(self, request_messages, response_messages, ...):
        ...
```

**SAM Solution**: HTTP-only integration via client libraries

```python
# Framework-agnostic client
class SAMClient:
    async def store_turn(self, user_msg: str, agent_msg: str) -> None:
        await self._http.post("/memory/store", json={...})
    
    async def retrieve(self, query: str, goal: str = None) -> RetrievalResult:
        return await self._http.post("/memory/retrieve", json={...})

# Framework adapters are thin wrappers
class SAMAgentFrameworkAdapter(ContextProvider):
    def __init__(self, sam_client: SAMClient):
        self.client = sam_client
    
    async def invoking(self, messages, **kwargs) -> Context:
        result = await self.client.retrieve(messages[-1].text)
        return Context(instructions=result.formatted_context)
```

### 4.2 CosmosDB-Specific Code ❌
**Files**: `memory/cosmos_utils.py` (to be abstracted)

**Reason**: Hard-coded Cosmos API calls prevent portability

**Current Problem**:
```python
# Directly uses Cosmos SDK
def execute_hybrid_search(
    self, container: ContainerProxy, query_embedding: list[float], ...
) -> list[dict]:
    query = """SELECT TOP @top_k c.id, c.content, ...
               VectorDistance(c.content_vector, @embedding) AS score
               FROM c WHERE c.user_id = @user_id"""
```

**SAM Solution**: MemoryStore interface with engine-specific implementations

---

## 5. Components to ADD (New for SAM)

### 5.1 Database Abstraction Layer 🆕
**New Files**: `memory/stores/base.py`, `memory/stores/sqlite_store.py`, `memory/stores/postgres_store.py`, `memory/stores/cosmos_store.py`

```python
# Abstract interface (from SAM_ARCHITECTURE.md)
class MemoryStore(Protocol):
    # Episode operations
    async def create_episode(self, ep: EpisodeCreate) -> str: ...
    async def get_episode(self, episode_id: str) -> Episode | None: ...
    
    # Entity operations
    async def get_or_create_entity(self, name: str, entity_type: str) -> str: ...
    async def get_entity(self, entity_id: str) -> Entity | None: ...
    async def find_entity_by_name(self, name: str) -> Entity | None: ...
    
    # Claim operations
    async def create_claim(self, claim: ClaimCreate) -> str: ...
    async def get_claims_for_entity(self, entity_id: str) -> list[Claim]: ...
    async def find_similar_claims(self, embedding: list[float], ...) -> list[Claim]: ...
    
    # Edge operations
    async def create_edge(self, edge: EdgeCreate) -> str: ...
    async def get_neighbors(self, node_id: str, edge_type: str = None) -> list[str]: ...
    
    # Retrieval
    async def hybrid_anchor_search(
        self, query_text: str, query_embedding: list[float], ...
    ) -> list[AnchorResult]: ...
    
    # Decay
    async def apply_decay(self, half_life_days: float = 30.0) -> int: ...
```

### 5.2 Spreading Activation Algorithm 🆕
**New Files**: `memory/retrieval/spreading_activation.py`

```python
class SpreadingActivation:
    """Goal-directed spreading activation retrieval."""
    
    def __init__(self, store: MemoryStore, config: SAMConfig):
        self.store = store
        self.config = config
    
    async def retrieve(
        self, 
        query: str, 
        goal: str = None,
        max_nodes: int = 50
    ) -> RetrievalResult:
        # 1. Anchor discovery (hybrid search)
        anchors = await self.store.hybrid_anchor_search(query, ...)
        
        # 2. Initialize activation heap
        heap = [(score, node_id) for score, node_id in anchors]
        activated = {}
        
        # 3. Spreading activation loop
        while heap and len(activated) < max_nodes:
            score, node_id = heapq.heappop(heap)
            if node_id in activated:
                continue
            
            activated[node_id] = score
            
            # Get neighbors and propagate
            neighbors = await self.store.get_neighbors(node_id)
            for neighbor_id in neighbors:
                neighbor = await self.store.get_node(neighbor_id)
                propagated = self._compute_propagation(
                    current_score=score,
                    edge_weight=edge.weight,
                    node=neighbor,
                    goal_embedding=goal_embedding
                )
                if propagated > self.config.activation_threshold:
                    heapq.heappush(heap, (propagated, neighbor_id))
        
        # 4. Filter and synthesize
        return self._synthesize_result(activated)
```

### 5.3 Entity/Claim Extraction Pipeline 🆕
**New Files**: `memory/ingestion/extractor.py`

```python
class EntityClaimExtractor:
    """Extract structured knowledge from episodes."""
    
    async def extract(
        self, 
        episode_content: str, 
        episode_id: str
    ) -> ExtractionResult:
        # LLM-based extraction with structured output
        result = await self.llm.parse(
            prompt=EXTRACTION_PROMPT.format(content=episode_content),
            output_type=ExtractionResult
        )
        
        return result  # Contains entities, claims, and their relationships
```

### 5.4 Graph Data Model 🆕
**New Files**: `memory/models/graph.py`

```python
class NodeType(str, Enum):
    EPISODE = "episode"
    ENTITY = "entity"
    CLAIM = "claim"
    INSIGHT = "insight"
    PROCEDURE = "procedure"

class EdgeType(str, Enum):
    MENTIONS = "MENTIONS"      # Episode → Entity
    ABOUT = "ABOUT"            # Claim → Entity
    SUPPORTS = "SUPPORTS"      # Claim → Claim or Claim → Insight
    CONTRADICTS = "CONTRADICTS"
    APPLIES = "APPLIES"        # Procedure → Insight/Claim

class Node(BaseModel):
    id: str
    tenant_id: str
    node_type: NodeType
    embedding: Optional[list[float]]
    strength: float = 1.0
    created_at: datetime
    last_accessed: datetime

class Edge(BaseModel):
    id: str
    source_id: str
    target_id: str
    edge_type: EdgeType
    weight: float = 1.0
    metadata: dict = {}
```

---

## 6. Architecture Diagram: Before vs After

### Current Architecture
```
┌─────────────────────────────────────────────────────────┐
│                 Agent (MS Agent Framework)               │
└────────────────────────┬────────────────────────────────┘
                         │ ContextProvider
┌────────────────────────▼────────────────────────────────┐
│  CosmosMemoryProvider (Embedded OR Remote)              │
│  ├── invoking() → inject context                        │
│  └── invoked() → store turn                             │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP (if remote)
┌────────────────────────▼────────────────────────────────┐
│  Memory Service (FastAPI)                                │
│  ├── SessionPool (in-memory)                            │
│  └── MemoryServiceOrchestrator                          │
│       ├── CurrentMemoryKeeper (turn buffer)             │
│       ├── ContextualFactRetrieval (CFR agent)           │
│       └── ReflectionProcess                             │
└────────────────────────┬────────────────────────────────┘
                         │ Cosmos SDK (direct)
┌────────────────────────▼────────────────────────────────┐
│  Azure CosmosDB                                          │
│  ├── interactions (multi-turn chunks + vectors)         │
│  ├── insights (session + long-term insights)            │
│  └── session_summaries                                  │
└─────────────────────────────────────────────────────────┘
```

### SAM Architecture
```
┌──────────────────────────────────────────────────────────┐
│  Any Agent Framework (MS Agent, LangGraph, etc.)         │
└────────────────────────┬─────────────────────────────────┘
                         │ Thin adapter (optional)
┌────────────────────────▼─────────────────────────────────┐
│  SAM Client (HTTP)                                        │
│  ├── store_turn()                                        │
│  ├── retrieve()                                          │
│  └── end_session()                                       │
└────────────────────────┬─────────────────────────────────┘
                         │ HTTP
┌────────────────────────▼─────────────────────────────────┐
│  SAM Service (FastAPI)                                    │  ← KEEP pattern
│  ├── SessionPool (in-memory)                             │  ← KEEP
│  └── SAMOrchestrator                                     │
│       ├── WorkingMemory (turn buffer)                    │  ← KEEP (refactor)
│       ├── IngestionPipeline                              │  ← NEW
│       │    └── EntityClaimExtractor                      │  ← NEW
│       ├── SpreadingActivationRetrieval                   │  ← NEW
│       └── ReflectionProcess                              │  ← KEEP (refactor)
└────────────────────────┬─────────────────────────────────┘
                         │ MemoryStore interface
┌────────────────────────▼─────────────────────────────────┐
│  MemoryStore (Abstract Interface)                        │  ← NEW
└────────┬──────────────┬─────────────────┬───────────────┘
         │              │                 │
   ┌─────▼─────┐  ┌─────▼─────┐    ┌─────▼─────┐
   │  SQLite   │  │ Postgres  │    │ CosmosDB  │
   │  + FTS5   │  │ + pgvector│    │ + vector  │
   │  + vec    │  │           │    │           │
   └───────────┘  └───────────┘    └───────────┘
     (default)    (production)     (Azure scale)
```

---

## 7. Implementation Plan

### Phase 1: Foundation (Week 1-2)
**Goal**: Database abstraction layer with SQLite default

| Task | Priority | Files | Effort |
|------|----------|-------|--------|
| Define MemoryStore interface | P0 | `memory/stores/base.py` | 2d |
| Implement SQLite store | P0 | `memory/stores/sqlite_store.py` | 3d |
| Define graph data models | P0 | `memory/models/graph.py` | 1d |
| Create storage factory | P0 | `memory/stores/factory.py` | 0.5d |
| Unit tests for SQLite store | P0 | `tests/test_sqlite_store.py` | 2d |

**Deliverable**: Working SQLite-based storage with Episode, Entity, Claim, Edge CRUD

### Phase 2: Ingestion Pipeline (Week 3)
**Goal**: Episode creation with entity/claim extraction

| Task | Priority | Files | Effort |
|------|----------|-------|--------|
| Entity/Claim extraction prompt | P0 | `memory/prompts/extraction.py` | 1d |
| Extraction pipeline | P0 | `memory/ingestion/extractor.py` | 2d |
| Refactor CurrentMemoryKeeper | P0 | `memory/working_memory.py` | 2d |
| Integration with store | P0 | `memory/ingestion/pipeline.py` | 1d |
| Tests | P1 | `tests/test_ingestion.py` | 1d |

**Deliverable**: Conversation turns → Episode + Entities + Claims

### Phase 3: Retrieval Algorithm (Week 4)
**Goal**: Spreading activation retrieval

| Task | Priority | Files | Effort |
|------|----------|-------|--------|
| Anchor search (hybrid) | P0 | `memory/retrieval/anchor.py` | 1d |
| Spreading activation | P0 | `memory/retrieval/spreading.py` | 3d |
| Goal-directed boost | P1 | (in spreading.py) | 1d |
| Synthesis/formatting | P0 | `memory/retrieval/synthesis.py` | 1d |
| Tests | P0 | `tests/test_retrieval.py` | 2d |

**Deliverable**: Query → Subgraph with activated nodes

### Phase 4: Service Refactor (Week 5)
**Goal**: Update server to use SAM components

| Task | Priority | Files | Effort |
|------|----------|-------|--------|
| SAMOrchestrator | P0 | `memory/sam_orchestrator.py` | 2d |
| Update server endpoints | P0 | `server/main.py` | 2d |
| SAMClient (HTTP) | P0 | `client/sam_client.py` | 1d |
| Remove embedded provider | P0 | Delete files | 0.5d |
| Integration tests | P0 | `tests/test_server.py` | 2d |

**Deliverable**: Working SAM service with HTTP API

### Phase 5: Additional Storage Engines (Week 6)
**Goal**: Postgres and Cosmos DB support

| Task | Priority | Files | Effort |
|------|----------|-------|--------|
| Postgres store | P1 | `memory/stores/postgres_store.py` | 3d |
| Cosmos DB store | P1 | `memory/stores/cosmos_store.py` | 3d |
| Engine-specific tests | P1 | `tests/test_postgres.py`, etc. | 2d |

**Deliverable**: Multi-engine support with engine selection

### Phase 6: Advanced Features (Week 7-8)
**Goal**: Decay, contradiction detection, insights

| Task | Priority | Files | Effort |
|------|----------|-------|--------|
| Decay mechanism | P1 | `memory/decay.py` | 2d |
| Claim consolidation | P2 | `memory/consolidation.py` | 2d |
| Insight distillation | P2 | `memory/reflection/insights.py` | 3d |
| Procedure extraction | P3 | `memory/reflection/procedures.py` | 2d |
| Framework adapters | P1 | `adapters/agent_framework.py`, `adapters/langgraph.py` | 2d |

**Deliverable**: Full SAM feature set

---

## 8. Migration Strategy

### 8.1 Data Migration
For existing CosmosDB data:

```python
async def migrate_cosmos_to_sam(cosmos_client, sam_store: MemoryStore):
    """Migrate existing CosmosDB documents to SAM graph."""
    
    # 1. Migrate users as Entities
    users = await cosmos_client.get_all_users()
    for user_id in users:
        await sam_store.get_or_create_entity(
            name=user_id,
            entity_type="user"
        )
    
    # 2. Migrate interactions as Episodes
    for interaction in cosmos_client.query_all_interactions():
        episode_id = await sam_store.create_episode(
            EpisodeCreate(
                source=f"migration:{interaction['id']}",
                raw_content=interaction['content'],
                summary=interaction['summary'],
                embedding=interaction['summary_vector'],
                metadata={
                    "legacy_id": interaction['id'],
                    "session_id": interaction['session_id']
                }
            )
        )
        
        # Re-extract entities and claims from content
        extraction = await extractor.extract(interaction['content'], episode_id)
        for entity in extraction.entities:
            await sam_store.get_or_create_entity(entity.name, entity.type)
        for claim in extraction.claims:
            await sam_store.create_claim(claim)
    
    # 3. Migrate long-term insights as SAM Insights
    for insight in cosmos_client.query_longterm_insights():
        await sam_store.create_insight(
            InsightCreate(
                content=insight['insight_text'],
                embedding=insight['insight_vector'],
                confidence=insight.get('confidence', 0.5)
            )
        )
```

### 8.2 API Compatibility Layer
Support gradual migration with backward-compatible endpoints:

```python
# Legacy endpoint (deprecated, forwards to SAM)
@app.post("/memory/store")
async def store_turn_legacy(request: StoreTurnRequest):
    # Forward to SAM ingestion
    return await sam_orchestrator.process_turn(
        user_msg=request.user_message,
        agent_msg=request.agent_message
    )

# New SAM endpoint
@app.post("/v2/memory/ingest")
async def ingest_episode(request: IngestRequest):
    return await sam_orchestrator.ingest_episode(request)
```

---

## 9. Risk Assessment

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Performance regression with spreading activation | High | Medium | Benchmark against CFR; tune parameters; add caching |
| Entity extraction quality | Medium | Medium | Multiple LLM providers; human-in-loop correction |
| Migration data loss | High | Low | Full backup; reversible migration; shadow mode testing |
| Framework adapter complexity | Medium | Medium | Keep adapters thin; test with real frameworks |
| SQLite scale limits | Medium | Low | Document limits (~10GB); Postgres upgrade path clear |

---

## 10. Success Criteria

| Metric | Current | SAM Target | Measurement |
|--------|---------|------------|-------------|
| Storage engine support | 1 (Cosmos) | 3 (SQLite, Postgres, Cosmos) | Engine tests pass |
| Framework support | 1 (MS Agent) | 2+ (MS Agent, LangGraph) | Adapter tests pass |
| Retrieval relevance | ~75% | ~85% | Human evaluation on test queries |
| Local-first startup | N/A | <1s with SQLite | Benchmark |
| Entity extraction | 0% | >80% accuracy | Human evaluation |
| Claim accuracy | N/A | >75% | Human evaluation |

---

## 11. Appendix: File Mapping

### Files to Keep (with modification)
| Current | SAM | Changes |
|---------|-----|---------|
| `server/main.py` | `server/main.py` | Update to use SAMOrchestrator |
| `memory/session_pool.py` | `memory/session_pool.py` | Minimal changes |
| `memory/config.py` | `memory/config.py` | Extend with SAM settings |
| `memory/current_memory_keeper.py` | `memory/working_memory.py` | Rename; refactor prune logic |
| `memory/reflection.py` | `memory/reflection/` | Split into claims/insights |
| `memory/models.py` | `memory/models/` | Add graph models |
| `memory/prompts.py` | `memory/prompts/` | Add extraction prompts |

### Files to Delete
| File | Reason |
|------|--------|
| `memory/cosmos_memory_provider_embedded.py` | Eliminated embedded mode |
| `memory/cosmos_agent_memory.py` | Replaced by SAMOrchestrator |
| `memory/cosmos_utils.py` | Replaced by MemoryStore interface |
| `memory/fact_retrieval.py` | Replaced by SpreadingActivation |

### New Files
| File | Purpose |
|------|---------|
| `memory/stores/base.py` | MemoryStore interface |
| `memory/stores/sqlite_store.py` | SQLite implementation |
| `memory/stores/postgres_store.py` | PostgreSQL implementation |
| `memory/stores/cosmos_store.py` | CosmosDB implementation |
| `memory/retrieval/spreading.py` | Spreading activation algorithm |
| `memory/retrieval/anchor.py` | Anchor search |
| `memory/retrieval/synthesis.py` | Result synthesis |
| `memory/ingestion/extractor.py` | Entity/Claim extraction |
| `memory/ingestion/pipeline.py` | Ingestion orchestration |
| `memory/models/graph.py` | Node/Edge models |
| `client/sam_client.py` | HTTP client |
| `adapters/agent_framework.py` | MS Agent Framework adapter |
| `adapters/langgraph.py` | LangGraph adapter |

---

## 12. Recommendation

**Proceed with SAM migration** following the phased approach above.

**Key priorities**:
1. **Phase 1-2** (Foundation + Ingestion): Establishes the new data model and proves the concept with SQLite
2. **Phase 3-4** (Retrieval + Service): Delivers a working replacement for current CFR
3. **Phase 5-6** (Engines + Features): Adds production capabilities

**Quick wins**:
- SQLite default enables local development without Azure
- Eliminating embedded mode simplifies the codebase by ~500 lines
- Graph model enables richer retrieval than flat document search

**Investment required**: ~8 weeks for full implementation, ~4 weeks for MVP (Phases 1-4)

---

**Document Status**: Ready for Review  
**Author**: Migration Analysis  
**Version**: 1.0
