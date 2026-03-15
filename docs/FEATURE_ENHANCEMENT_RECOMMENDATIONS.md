# Feature Enhancement Recommendations — Agent Memory Service

## mem0 vs Agent Memory Service — Comparison

| Capability | mem0 | Agent Memory Service | Verdict |
|---|---|---|---|
| **Memory extraction** | LLM extracts individual facts from conversations | Tiered: turn buffer → cumulative summary → interaction chunks → insights → profile | Agent Memory has more nuanced tiering |
| **Conflict resolution** | Automatic dedup with "latest truth wins" via ADD/UPDATE/DELETE/NONE actions | No automatic dedup; insight reflection can merge but doesn't track conflicts | **mem0 is better** |
| **Graph memory** | Neo4j, Memgraph, Neptune, Kuzu — entities + relationships | Not implemented (archived SAM had spreading activation) | **mem0 is better** |
| **Forgetting/decay** | Only expiration dates (Platform only) | Ebbinghaus forgetting curve with access tracking | **Agent Memory is better** |
| **Memory scoring** | Cosine similarity + optional reranker + keyword search | Cosine similarity + hybrid search, with backend-native ranking preferred over a custom reranker | Gap is narrowing |
| **Vector backends** | 19+ (Qdrant, Pinecone, Chroma, PGVector, etc.) | 4 (SQLite, CosmosDB, Azure AI Search, PostgreSQL) | mem0 still has broader backend coverage |
| **LLM backends** | 15+ providers | Azure OpenAI only | **mem0 is better** |
| **Selective memory** | Custom extraction prompts with few-shot examples | Fixed prompt templates | **mem0 is better** |
| **Multi-scope** | user_id + agent_id + session_id + run_id | user_id + agent_id + session_id (`run_id` deferred) | Gap is narrowing |
| **Session management** | Minimal (stateless add/search) | Full lifecycle (start → turns → summarize → reflect → end) | **Agent Memory is better** |
| **Agent Framework integration** | Multiple (LangChain, CrewAI, AutoGen) | Deep MS Agent Framework integration (BaseContextProvider) | Different approach |
| **Multimodal** | Images + documents | Text only | **mem0 is better** |
| **Memory categories** | Auto-categorization with custom categories | Category field on insights but no auto-tagging | **mem0 is better** |
| **REST API** | FastAPI with OpenAPI docs | FastAPI with session-oriented endpoints | Comparable |
| **Export/import** | Schema-driven export, raw import with infer=False | Not implemented | **mem0 is better** |

---

## What Agent Memory Does Better

1. **Session-aware memory lifecycle** — The tiered system (active turns → cumulative summary → interactions → insights → profile) mirrors how human memory works. mem0 is more stateless.

2. **Ebbinghaus forgetting curve** — `insight_items.py` implements genuine memory decay with access tracking, retention scoring, and bounded memory. mem0 has nothing comparable in OSS.

3. **Cumulative summarization** — Rolling session summaries via LLM provide compressed context without losing continuity. mem0 stores individual facts but doesn't maintain session narratives.

4. **Agent Framework as context provider** — Automatic `before_run`/`after_run` hooks for transparent memory injection. More deeply integrated than mem0's adapter approach.

---

## Recommended Features to Implement

### Priority 1 — Close the biggest gaps

#### 1. Automatic conflict resolution / deduplication

Currently, insights accumulate without checking for contradictions or duplicates. A user saying "I prefer Python" and later "I switched to Rust" should update, not create two conflicting memories. This is the single most impactful missing feature.

**How mem0 implements this (reference design):**

mem0 uses a two-LLM-call pipeline on every `add()`:

1. **Fact extraction** — LLM extracts atomic facts from the conversation as a JSON array (`{"facts": ["Name is John", "Likes pizza"]}`)
2. **Conflict resolution** — For each extracted fact, embed it and vector-search the top 5 nearest existing memories. Collect all candidates, deduplicate by ID, then send a single LLM call with both old memories and new facts. The LLM returns a JSON array of actions:

```json
{
    "memory": [
        {"id": "0", "text": "Loves cheese and chicken pizza", "event": "UPDATE", "old_memory": "Likes cheese pizza"},
        {"id": "5", "text": "Name is John", "event": "ADD"},
        {"id": "2", "text": "Loves cheese pizza", "event": "DELETE"},
        {"id": "1", "text": "User is a software engineer", "event": "NONE"}
    ]
}
```

**Key design decisions in mem0:**
- **UUID → integer remapping**: Existing memory IDs are remapped to simple integers (0, 1, 2...) before sending to the LLM to prevent UUID hallucination. Mapped back after response.
- **Contradictions = DELETE + ADD, not UPDATE**: "Loves pizza" → "Dislikes pizza" results in DELETE of the old memory, with the new fact ADDed separately.
- **Richer info wins for same-topic**: "Likes cricket" → "Loves cricket with friends" results in UPDATE because the new fact adds detail.
- **Identical meaning = NONE**: "Likes cheese pizza" vs "Loves cheese pizza" = no change.
- **Full replacement, not merge**: The LLM produces the final merged text in its response. Code stores it as-is and re-embeds.
- **Audit trail**: Every mutation (ADD/UPDATE/DELETE) is recorded in a history table with `old_memory`, `new_memory`, `event`, and timestamps.

**Proposed implementation for Agent Memory Service:**

Integrate conflict resolution into the existing `Reflection` pipeline during insight extraction:

1. After extracting new session insights, embed each insight and vector-search existing `long_term_item` insights (top 5 per insight)
2. Send a single conflict resolution LLM call with the existing insights and new insights, using a prompt that returns ADD/UPDATE/DELETE/NONE actions
3. Execute actions: ADD creates new `LongTermInsightItem`, UPDATE replaces text + re-embeds + preserves `date_added`/`access_count`, DELETE removes the insight
4. Record mutations in a new `insight_history` field or separate audit log
5. Use integer ID remapping (INS-0001 → 0, 1, 2...) to prevent hallucination

Add a `CONFLICT_RESOLUTION_PROMPT` to `memory/prompts.py` with clear guidelines and few-shot examples for each action type. Allow override via `AgentMemoryConfig.custom_conflict_resolution_prompt`.

**Affected files:** `memory/core/reflection.py`, `memory/core/insight_items.py`, `memory/prompts.py`, `memory/models.py` (audit model)

#### 2. Custom extraction prompts

Let users configure what types of facts to extract via custom prompts with few-shot examples. Add a `custom_extraction_prompt` field to `AgentMemoryConfig`. This enables domain-specific memory without forking the code and fixes the existing issue where `LONGTERM_SYNTHESIS_PROMPT` is hardcoded for the financial advisor domain.

**Affected files:** `memory/core/agent_memory.py`, `memory/prompts.py`, `memory/core/reflection.py`, `memory/core/memory_keeper.py`

#### 3. `agent_id` and `run_id` scoping

Add `agent_id` to all document types and queries alongside `user_id`/`session_id`. Enables multi-agent architectures where different agents maintain separate memories for the same user. For example, a shopping assistant and a health assistant can each have independent memory stores for the same user.

**Affected files:** `memory/models.py`, `memory/db/base.py`, `memory/db/sqlite_backend.py`, `memory/db/cosmos_backend.py`, `memory/core/agent_memory.py`

#### 4. Backend-native ranking strategy (no standalone reranker)

Do not add a repo-owned reranking layer. Use hybrid search now, then rely on backend-native ranking when available, especially Azure AI Search semantic ranking. This avoids introducing another provider surface for a capability that Azure-native infrastructure already provides or is about to provide.

**Affected files:** docs, backend selection/config, future Azure AI Search integration

### Priority 2 — Differentiated enhancements

#### 5. Keyword / hybrid search

CosmosDB already implements hybrid search with RRF (vector + full-text via `FullTextScore`) in `cosmos_backend.py`, but it is not wired into the `FactRetrieval` layer — searches always go through `vector_search()` instead of `hybrid_search()`. The work here is:

1. **Wire hybrid search into FactRetrieval** — When the backend supports it (`capabilities.supports_hybrid_search`), route queries through `hybrid_search()` instead of `vector_search()`. This activates the existing CosmosDB RRF implementation.
2. **Add SQLite FTS5 support** — SQLite FTS5 is already available and could be added to the existing tables for keyword matching. Implement `hybrid_search()` on `SQLiteDatabase` using FTS5 + vector similarity with a simple score fusion.
3. **Expose hybrid search in the API** — Add a `search_mode` parameter to `AgentMemory.search()` allowing callers to choose between `vector`, `keyword`, or `hybrid`.

**Affected files:** `memory/core/fact_retrieval.py` (route to hybrid when available), `memory/db/sqlite_backend.py` (add FTS5 + hybrid), `memory/core/agent_memory.py` (expose search_mode)

#### 6. Memory categories with auto-tagging

Auto-classify memories into configurable categories during extraction. Enable category-based filtering in search. The `category` field already exists on `SessionInsightDocument` — extend it with LLM-based auto-tagging and a configurable category list.

mem0's default categories: `personal_details`, `family`, `professional_details`, `sports`, `travel`, `food`, `music`, `health`, `technology`, `hobbies`, `fashion`, `entertainment`, `milestones`, `user_preferences`, `misc`.

**Affected files:** `memory/core/reflection.py`, `memory/core/insight_items.py`, `memory/prompts.py`, `memory/core/agent_memory.py` (config)

#### 7. Memory export / import

Export memories as structured JSON with schema control. Import with a raw mode (skip LLM extraction) for bulk loading. Essential for migration, backup, debugging, and compliance data requests.

**Affected files:** `memory/core/agent_memory.py` (new `export_memories()` / `import_memories()` methods), `server/main.py` (new endpoints)

### Priority 3 — Azure backend expansion

#### 8. Azure AI Search backend

Add Azure AI Search as a vector store backend. Azure AI Search provides managed vector search with built-in hybrid search (BM25 + vector via RRF), semantic reranking, filtering, and integrated security via Entra ID. This would replace the need for a separate reranker (#4) since Azure AI Search has native semantic ranking built in.

**Key capabilities:**
- Native vector search with HNSW and exhaustive KNN indexing
- Built-in hybrid search (keyword + vector) with RRF fusion
- Semantic ranker for reranking results using Microsoft's cross-encoder models
- Rich filtering on metadata fields
- Managed infrastructure with SLA, scaling, and geo-replication
- Entra ID RBAC integration for secure multi-tenant access

**New files:** `memory/db/azure_search_backend.py`, update `memory/db/factory.py` with `DatabaseType.AZURE_AI_SEARCH`

#### 9. Azure PostgreSQL with pgvector backend

Add Azure Database for PostgreSQL Flexible Server with the pgvector extension as a backend. PostgreSQL provides a familiar relational model with strong consistency guarantees, mature tooling, and pgvector for vector similarity search. Good for teams already using PostgreSQL or needing ACID transactions across memory operations.

**Key capabilities:**
- pgvector extension for vector similarity search (IVFFlat, HNSW indexes)
- Full SQL query capabilities and joins across memory tiers
- ACID transactions for atomic batch operations (fixes SQLite transactional issues)
- Native full-text search via tsvector for hybrid search
- Azure managed service with Entra ID authentication
- Familiar migration tooling (Alembic, etc.)

**New files:** `memory/db/postgresql_backend.py`, update `memory/db/factory.py` with `DatabaseType.POSTGRESQL`

#### 10. Pluggable LLM abstraction

Support OpenAI (direct), Anthropic, Ollama, and LiteLLM in addition to Azure OpenAI. The `_call_llm_with_json` pattern is already centralized in two places — extract it into a provider interface similar to `EmbeddingProvider`.

**New files:** `memory/providers/llm.py` with `LLMProvider` protocol and implementations

### Priority 4 — Additional enhancements

#### 11. Multimodal memory

Accept image/document inputs alongside text. Use vision models or document extractors to convert to text before memory processing. Growing need as agents handle more media types.

**Affected files:** `memory/core/agent_memory.py` (`add_turn` to accept attachments), `memory/core/memory_keeper.py`

#### 12. Immutable memories

Flag certain memories as immutable (cannot be updated/deleted via normal operations). Useful for compliance, system-level facts, or user-confirmed preferences. mem0 implements this as a simple boolean flag.

**Affected files:** `memory/models.py`, `memory/db/base.py`, `memory/core/insight_items.py`

#### 13. Graph memory layer

Extract entities and relationships from conversations. Store in a graph backend (Neo4j or embedded Kuzu for lightweight deployments). Enrich vector search results with relationship context. This was partially explored in the archived SAM spreading activation implementation — could revive the concept with modern graph databases.

**New files:** `memory/db/graph_base.py`, `memory/db/neo4j_backend.py` or `memory/db/kuzu_backend.py`, `memory/core/graph_extraction.py`

---

## Implementation Sequencing

| Phase | Focus | Items | Estimated Scope |
|---|---|---|---|
| 1 | Close critical gaps | Conflict resolution, custom prompts, agent_id scoping | Core library changes |
| 2 | Search quality | Hybrid search, backend-native ranking policy, auto-categorization | Retrieval + DB layer |
| 3 | Azure backends | Azure AI Search backend, Azure PostgreSQL backend | New DB backends |
| 4 | Data management | Export/import, immutable memories | API + storage layer |
| 5 | Ecosystem | Pluggable LLMs, multimodal, graph memory | Provider abstractions |

---

## Summary

Agent Memory Service has a more sophisticated memory lifecycle model than mem0 — the tiered system and Ebbinghaus forgetting curve are genuinely innovative. However, mem0 still leads in backend flexibility, graph memory, and customization breadth. The highest-impact improvements here are automatic dedup/conflict resolution (#1), custom extraction prompts (#2), multi-agent scoping (#3), hybrid search plus backend-native ranking strategy (#4/#5), and Azure AI Search followed by PostgreSQL (#8/#9).

---

## Implementation Planning Addendum

This section reflects a repo-specific implementation plan based on the current code layout in `memory/core/reflection.py`, `memory/core/fact_retrieval.py`, `memory/models.py`, `memory/core/agent_memory.py`, and the current SQLite/CosmosDB backends. The recommendations above are directionally strong, but the implementation order should be adjusted to fit the code that exists today.

### Overall Position

- Agree strongly with `#1` automatic conflict resolution / deduplication as the top product-quality improvement.
- Agree with `#2` custom prompts and `#6` auto-categorization as near-term work because the reflection pipeline already owns these semantics.
- Agree with `#3` multi-scope support, but recommend implementing `agent_id` first and explicitly deferring `run_id` until there is a concrete retrieval or audit use case.
- Disagree with implementing a standalone `#4` reranker at all. Hybrid search is the immediate win, and ranking improvements should come from backend-native capabilities such as Azure AI Search semantic ranking.
- Recommend moving `#7` export/import earlier because schema churn is likely during conflict resolution and scoping work.
- Recommend deferring `#13` graph memory until the core memory mutation model is stable.

### Revised Implementation Waves

#### Wave 1 — Memory semantics and extraction quality

Implement `#1`, `#2`, and `#6` together because they all belong in the reflection path.

- Add conflict resolution after session-insight extraction and before long-term insight persistence.
- Add configurable extraction prompts and conflict-resolution prompts to `AgentMemoryConfig`.
- Standardize configurable category lists and use them during extraction and synthesis.
- Add mutation audit records for `ADD`, `UPDATE`, `DELETE`, and `NONE`.

Primary files:
- `memory/core/reflection.py`
- `memory/core/insight_items.py`
- `memory/prompts.py`
- `memory/models.py`
- `memory/core/agent_memory.py`

Notes:
- Use integer remapping for LLM-facing IDs to reduce hallucinated updates.
- Preserve retention-related metadata when updating an existing insight.
- Treat direct contradictions as `DELETE + ADD`, not `UPDATE`.

#### Wave 2 — Retrieval quality

Implement `#5` and the `#4` backend-native ranking policy together.

- Route retrieval through backend capability detection so `FactRetrieval` can use hybrid search when available.
- Expose `search_mode` in the library and server API with `vector`, `keyword`, and `hybrid`.
- Add SQLite FTS5-backed keyword/hybrid search.
- Do not add a standalone reranker provider; defer ranking improvements to backend-native support.

Primary files:
- `memory/core/fact_retrieval.py`
- `memory/core/agent_memory.py`
- `memory/db/sqlite_backend.py`
- `memory/db/cosmos_backend.py`
- `memory/db/base.py`
- `server/main.py`
- `client/memory_client.py`

Notes:
- CosmosDB already advertises hybrid-search capability, so that path should be activated rather than redesigned.
- SQLite should use simple score fusion first; do not block on a perfect ranking formula.

#### Wave 3 — Scoping and portability

Implement `#3` and `#7`, but scope `#3` to `agent_id` in this pass.

- Add `agent_id` to persisted documents, constructors, search filters, and server request models.
- Keep `run_id` deferred until there is a clear lifecycle contract for it.
- Add versioned export/import methods and server endpoints.
- Support raw import mode that bypasses extraction/reflection for migration and test-fixture loading.

Primary files:
- `memory/models.py`
- `memory/db/base.py`
- `memory/db/sqlite_backend.py`
- `memory/db/cosmos_backend.py`
- `memory/core/agent_memory.py`
- `memory/core/orchestrator.py`
- `server/main.py`

Notes:
- Export/import will help with validation while evolving schemas and conflict-resolution behavior.
- `agent_id` should default cleanly so existing single-agent usage can still be represented without ambiguity.

#### Wave 4 — Provider abstraction

Implement `#10` after the reflection and retrieval semantics settle.

- Add an `LLMProvider` abstraction for structured JSON generation and synthesis calls.
- Migrate reflection/synthesis first; leave embeddings as a separate provider abstraction.
- Keep the public `AgentMemory` interface stable while swapping internal provider wiring.

Primary files:
- new `memory/providers/llm.py`
- `memory/core/llm_json.py`
- `memory/core/reflection.py`
- `memory/core/memory_keeper.py`
- `memory/core/orchestrator.py`

#### Wave 5 — Additional backends

Implement `#8` first, then `#9`.

- Do Azure AI Search first for Azure-native hybrid retrieval and managed ranking.
- Do PostgreSQL second for transactional consistency, SQL visibility, and operational familiarity.

Primary files:
- `memory/db/factory.py`
- new backend modules
- backend-specific tests and docs

#### Wave 6 — Follow-on enhancements

Defer these until the memory mutation model and scoping model are stable.

- `#12` immutable memories
- `#11` multimodal memory
- `#13` graph memory

### Item-by-Item Disposition

- `#1` Do now.
- `#2` Do now.
- `#3` Partially now: `agent_id` yes, `run_id` later.
- `#4` Replace with backend-native ranking only; no standalone reranker.
- `#5` Pull forward.
- `#6` Do with Wave 1.
- `#7` Pull forward with scoping/schema work.
- `#8` Do next.
- `#9` Do after `#8`.
- `#10` Medium priority after semantics stabilize.
- `#11` Defer.
- `#12` Medium priority after conflict resolution exists.
- `#13` Defer until post-stabilization.

### Concrete Test Strategy

- Add conflict-resolution regression tests for duplicate, contradiction, enrichment-update, and no-op cases.
- Add hybrid-search parity tests across SQLite and CosmosDB.
- Add schema/filter tests for `agent_id` propagation across writes and searches.
- Add export/import round-trip tests with raw mode and version validation.
- Add prompt-override tests for custom extraction and conflict-resolution prompts.
- Re-run live Azure OpenAI + CosmosDB smoke tests after Waves 1 through 3.

### Practical Risks

- Conflict resolution can over-delete unless prompts are tightly bounded and audited.
- Adding `agent_id` too late will make later migrations harder; adding `run_id` too early will create churn.
- A standalone reranker would add another provider surface for limited payoff when Azure-native ranking can own that concern later.
- Graph memory should not be started until insight mutation and audit semantics are trustworthy.
