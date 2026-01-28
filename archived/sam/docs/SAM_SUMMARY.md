# 🧠 SAM: Spreading Activation Memory - Summary

This is a condensed overview of the full design. See [SAM_ARCHITECTURE.md](SAM_ARCHITECTURE.md) for complete specifications.

---

## Why "Spreading Activation"?

SAM is inspired by how human memory actually works: **cues activate anchor nodes, activation spreads through learned associations, and the strongest activations surface**. This isn't vector similarity search — it's cognitive retrieval.

---

## 1. Goals

**Primary Goals:**
- Ground memory in experience (auditability): everything learned traces back to Episodes
- Support living knowledge: Claims and Insights gain/lose strength over time
- Enable multi-modal retrieval: hybrid anchors + spreading activation
- Abstract storage engines: same logical model across SQLite, Postgres, Cosmos DB
- Default to local-first: SQLite with vector search + FTS

**Non-Goals:**
- Building a full ontology taxonomy
- Enforcing a specific graph database

---

## 2. Ontology (5 Node Types)

```
Episode → Entity → Claim → Insight → Procedure
```

### Episode
**What**: A chat session that accumulates conversation turns from working memory
**Purpose**: Ground all memory in real experience, enable auditability

**Lifecycle**:
- Working memory buffer holds active turns (in-memory, unstructured)
- Flushed turns are **appended** to the current open Episode
- New Episode starts when size exceeds limit (default: **10,000 tokens**)
- Episode close triggers reflection (Entity/Claim extraction)

### Entity
**What**: A stable reference to a person, system, object, or abstract concept
**Purpose**: Anchor memory to real-world actors/things, enable personalization

### Claim
**What**: An atomic, descriptive claim about one or more Entities
**Purpose**: Capture "what is/was true" about specific Entities

**Key Constraint**: Every Claim MUST have at least one `ABOUT` edge to an Entity

| Claim (descriptive) | NOT a Claim |
|--------------------|------------|
| "User:Alice prefers email" | Generic observation without entity |
| "Billing escalates after 48h" → ABOUT → Entity:BillingProcess | Actionable recommendation |

### Insight
**What**: A generalized, actionable heuristic derived from Claims
**Purpose**: Answer "what should we do?" - prescriptive, not descriptive

| Insight (prescriptive) | NOT an Insight |
|------------------------|----------------|
| "Offer proactive outreach before 48h for billing" | "Billing issues escalate after 48h" (this is a Claim) |

### Procedure (Optional)
**What**: A reusable, executable workflow derived from high-confidence Insights
**Lifecycle**: Genesis → Validation → Activation → Versioning → Deprecation

---

## 3. Relationships

### Edge Types
| Edge | From → To | Purpose |
|------|-----------|---------|
| `INVOLVES` | Episode → Entity | Who/what participated |
| `PRODUCED` | Episode → Claim | What was learned |
| `ABOUT` | Claim → Entity | **Required**: anchors Claim to entity |
| `RELATED_TO` | Entity → Entity | General relationships |
| `SUPPORTS` | Claim → Insight | Evidence chain |
| `CONTRADICTS` | Claim → Claim | Conflicting claims |
| `INFLUENCES` | Insight → Procedure | Action derivation |

### Edge Weight Updates
- Reinforcement: `w ← min(1, w + η × (1 - w))`
- Decay: `w ← w × (1 - γ)`

---

## 4. Storage Engine Abstraction

### Supported Engines
| Engine | Vector | Lexical | Graph | Use Case |
|--------|--------|---------|-------|----------|
| **SQLite** (default) | sqlite-vec | FTS5 | Recursive CTEs | Local development |
| PostgreSQL | pgvector | tsvector | CTEs / Apache AGE | Production cloud |
| Cosmos DB | Native | Native | Gremlin API | Azure deployment |

### Multi-Tenancy
- All tables include `tenant_id` column (not in metadata JSON)
- All queries MUST filter by tenant_id
- Edges also have tenant_id for strict isolation

### Key Schema (SQLite)
```sql
CREATE TABLE nodes (
  node_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  node_type TEXT NOT NULL,  -- Episode|Entity|Claim|Insight|Procedure
  content TEXT NOT NULL,
  embedding BLOB,
  confidence REAL DEFAULT 0.8,
  claim_kind TEXT,           -- preference|constraint|profile|operational
  temporal_scope TEXT,      -- past|current|future
  created_at TEXT,
  updated_at TEXT,
  ...
);

CREATE TABLE edges (
  edge_id TEXT PRIMARY KEY,
  tenant_id TEXT NOT NULL,
  src_id TEXT, dst_id TEXT,
  edge_type TEXT,
  weight REAL DEFAULT 1.0,
  ...
);
```

---

## 5. MemoryStore Interface (Key Methods)

```python
class MemoryStore(Protocol):
    # Node operations
    async def upsert_node(self, node: NodeRecord) -> NodeRecord
    async def get_node(self, tenant_id: str, node_id: str) -> Optional[NodeRecord]
    async def get_nodes(self, tenant_id: str, node_ids: Sequence[str]) -> Dict[str, NodeRecord]
    
    # Search operations (all require tenant_id via filters)
    async def lexical_search(self, query: str, filters: SearchFilters, limit: int) -> List[Anchor]
    async def vector_search(self, embedding: List[float], filters: SearchFilters, limit: int) -> List[Anchor]
    async def entity_name_search(self, name: str, tenant_id: str, limit: int) -> List[Anchor]
    
    # Entity resolution cascade
    async def find_entity_exact(self, tenant_id: str, name: str) -> Optional[NodeRecord]
    async def find_entity_by_alias(self, tenant_id: str, alias: str) -> Optional[NodeRecord]
    async def find_entity_fuzzy(self, tenant_id: str, name: str, threshold: float) -> Optional[NodeRecord]
    async def find_entity_semantic(self, tenant_id: str, embedding: List[float], threshold: float) -> Optional[NodeRecord]
    
    # Graph traversal
    async def get_neighbors(self, tenant_id: str, node_id: str, ...) -> List[Tuple[str, str, float, int]]
    async def shortest_path(self, tenant_id: str, src_id: str, dst_id: str, max_depth: int) -> Optional[List]
```

---

## 6. Retrieval Algorithm

### Pipeline
```
Query → Anchor Discovery → Spreading Activation → Filtering → Reasoning Chain → Synthesis
```

### Step 1: Anchor Discovery
1. **Deterministic**: Known user entity (score=1.0)
2. **Entity match**: Fast name lookup (score=1.0)
3. **Semantic**: Vector similarity (score=cosine_sim)
4. **Keyword**: Lexical search (score=0.7×match)

### Step 2: Spreading Activation
Two key enhancements over basic BFS:

**Degree Penalty (Hub Dampening)**:
```
penalty = min(1.0, max(0.1, 5.0 / √degree))
```
Nodes with degree 400 pass only 25% of activation.

**Goal-Directed Boost**:
```
goal_mult = 0.5 + 0.5 × sim(goal_embedding, node_embedding)
```
Relevant nodes get boosted during traversal, not filtered after.

**Combined Formula**:
```
activation_next = activation × 0.7 × edge_type_weight × edge_weight × degree_penalty × goal_mult
```

### Step 3: Filtering
- Recency boost: `exp(-days_old / 30)`
- Per-type caps: Entity(5), Claim(15), Insight(5), Episode(3)
- Top-k selection (default 20)

### Step 4: Reasoning Chain
Shortest paths between high-activation nodes (up to 10 steps)

### Step 5: Synthesis
Return `RetrievalResponse` with entities, Claims, insights, procedures, anchors, reasoning chain

---

## 7. Ingestion Algorithm

### Pipeline
```
Content → Episode → Entity Resolution → Claim Extraction → Edge Updates → Insight Distillation
```

### Step 1: Create Episode
Store raw content with embedding, source, session_id (as metadata)

### Step 2: Entity Resolution
Cascade: exact → alias → fuzzy (0.85) → semantic (0.9)
- Match found: update aliases, reuse entity
- No match: create new entity

### Step 3: Claim Extraction
- **Validation**: Skip Claims without entity references
- **Similarity check**: Find existing Claim about same entity (threshold 0.85)
- **LLM Classification**: If similar Claim exists, classify relationship

| Relationship | Action |
|--------------|--------|
| IDENTICAL | Merge evidence, boost confidence |
| REINFORCING | Boost existing, also create new |
| CONTRADICTING | Reduce old confidence 50%, add CONTRADICTS edge |
| SUPERSEDING | Archive old, create new |

### Step 4: Entity-Entity Relationships
Extract and strengthen or create edges between entities

### Step 5: Insight Distillation (Batch)
When entity has ≥3 Claims with confidence ≥0.5, generate insights via LLM

---

## 8. Decay Mechanism

### Claim-Kind Aware Decay
| claim_kind | decay_rate | min_confidence |
|-----------|------------|----------------|
| operational | 0.005 | 0.3 |
| profile | 0.01 | 0.2 |
| preference | 0.03 | 0.1 |
| constraint | 0.01 | 0.25 |

### Temporal Scope Multiplier
| temporal_scope | multiplier |
|----------------|------------|
| past | 2.0× (faster decay) |
| current | 1.0× |
| future | 0.5× (slower decay) |

### Formula
```
c(t) = max(min_confidence, c₀ × exp(-rate × temporal_mult × days_since_access))
```

### Reinforcement on Access
When node is retrieved: reset decay timer, boost confidence slightly

---

## 9. LLM Contradiction Detection

### 6-Way Classification
| Relationship | Meaning |
|--------------|---------|
| IDENTICAL | Same information |
| REINFORCING | Compatible, supports each other |
| INDEPENDENT | Different aspects, no relationship |
| CONTRADICTING | Mutually exclusive |
| SUPERSEDING | Temporal update (old was true, now new is) |
| REFINING | More specific version |

### Cost Optimization
1. Pre-filter with embeddings (only call LLM if sim > 0.7)
2. Batch processing
3. Skip low-confidence Claims (< 0.3)

---

## 10. Feedback Loop

### Signals
- Explicit thumbs up/down
- Context used in LLM response
- User corrections
- Task success metrics

### Application
- Positive feedback: boost node confidence
- Negative feedback: dampen unused retrieved nodes
- Marked incorrect: significant penalty, flag for review after 3×

---

## 11. Implementation Tiers

### Tier 1: MVP
| Include | Defer |
|---------|-------|
| Episode, Entity, Claim | Insight, Procedure |
| SQLite only | Postgres, Cosmos |
| Vector + lexical, simple BFS | Goal-directed activation |
| Basic ingestion | Insight distillation |
| No decay | All decay logic |
| Embedding similarity only | LLM contradiction |
| Single tenant | Multi-tenancy |

### Tier 2: Production
| Add |
|-----|
| Insight nodes |
| PostgreSQL adapter |
| Goal-directed activation, degree penalty |
| Insight distillation |
| Basic time-based decay |
| LLM contradiction (batch) |
| Row-level tenant isolation |

### Tier 3: Full Featured
| Add |
|-----|
| Procedure nodes + lifecycle |
| Cosmos DB adapter |
| Full claim_kind aware decay |
| Real-time LLM classification |
| Full feedback loop |
| System tenant for shared knowledge |

---

## 12. Key Design Decisions

1. **Claims are entity-bound**: No orphan Claims floating without entity context
2. **Claim vs Insight boundary**: Descriptive vs prescriptive (clear separation)
3. **Multi-tenant by default**: tenant_id in schema, not metadata
4. **Goal-directed activation**: Boost during spreading, not filter after
5. **Degree penalty**: Dampen hub nodes to prevent activation flooding
6. **Claim-kind aware decay**: Operational Claims decay slower than preferences
7. **LLM for contradictions**: Embedding similarity alone is insufficient
8. **Tiered implementation**: MVP first, add complexity as needed

---

## 13. API Surface

```
POST /memory/episodes     # Ingest episode
POST /memory/retrieve     # Retrieve context pack
GET  /memory/nodes/{id}   # Inspect node (debug)
```

---

## Quick Reference

### Node Types
```
Episode (what happened) → Entity (who/what) → Claim (what's true) → Insight (what to do) → Procedure (how to do it)
```

### Required Edges
- Claim → Entity via `ABOUT` (at least one)
- Episode → Claim via `PRODUCED`
- Episode → Entity via `INVOLVES`

### Retrieval Formula
```
activation = anchor_score × 0.7^depth × edge_weight × (5/√degree) × (0.5 + 0.5×goal_sim)
```

### Decay Formula
```
confidence = max(floor, c₀ × exp(-rate × temporal_mult × days))
```
