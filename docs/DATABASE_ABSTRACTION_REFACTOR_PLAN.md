# Database Abstraction Refactoring Plan

## Executive Summary

This document outlines the plan to consolidate the Agent Memory Service to use a unified database abstraction layer that supports multiple backends (SQLite, CosmosDB, future PostgreSQL).

**Current State:** Two parallel implementations exist - CosmosDB bypasses the abstraction layer, SQLite uses it.

**Target State:** Single unified implementation using `memory/db/` abstraction with backend selection via configuration.

---

## 1. Current Architecture Analysis

### 1.1 Existing File Structure

```
memory/
├── db/                              # ✅ Database abstraction layer (KEEP)
│   ├── base.py                      # Abstract MemoryDatabase interface
│   ├── sqlite_backend.py            # SQLite implementation
│   ├── cosmos_backend.py            # CosmosDB implementation
│   ├── factory.py                   # Factory pattern
│   └── adapters.py                  # Compatibility adapters
│
├── cosmos_agent_memory.py           # ❌ CosmosDB-specific (TO CONSOLIDATE)
├── sqlite_agent_memory.py           # ❌ SQLite-specific (TO CONSOLIDATE)
├── orchestrator.py                  # ❌ CosmosDB-specific (TO CONSOLIDATE)
├── sqlite_orchestrator.py           # ❌ SQLite-specific (TO CONSOLIDATE)
├── cosmos_utils.py                  # ❌ CosmosDB-specific (TO RETIRE)
├── cosmos_memory_provider.py        # ❌ CosmosDB-specific (TO CONSOLIDATE)
├── sqlite_memory_provider.py        # ❌ SQLite-specific (TO CONSOLIDATE)
│
├── config.py                        # ✅ Configuration (KEEP)
├── models.py                        # ✅ Data models (KEEP)
├── current_memory_keeper.py         # 🔄 Uses containers directly (REFACTOR)
├── fact_retrieval.py                # 🔄 Uses containers directly (REFACTOR)
├── reflection.py                    # 🔄 Uses containers directly (REFACTOR)
└── prompts.py                       # ✅ LLM prompts (KEEP)
```

### 1.2 Dependency Graph

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Current Architecture                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  CosmosDB Path (Direct)              SQLite Path (Abstracted)        │
│  ──────────────────────              ────────────────────────        │
│                                                                      │
│  CosmosAgentMemory                   SQLiteAgentMemory               │
│       │                                   │                          │
│       ▼                                   ▼                          │
│  MemoryServiceOrchestrator          SQLiteMemoryOrchestrator         │
│       │                                   │                          │
│       ├─► CurrentMemoryKeeper            Uses embedded logic         │
│       ├─► ContextualFactRetrieval         │                          │
│       ├─► ReflectionProcess               ▼                          │
│       │                              MemoryDatabase (base.py)        │
│       ▼                                   │                          │
│  CosmosUtils (embedding)                  ▼                          │
│       │                              SQLiteDatabase                  │
│       ▼                                                              │
│  ContainerProxy (Azure SDK)                                          │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 1.3 Code Duplication Analysis

| Component | CosmosDB | SQLite | Duplication |
|-----------|----------|--------|-------------|
| Agent Memory | 426 lines | 663 lines | ~70% logic similar |
| Orchestrator | 767 lines | 717 lines | ~85% logic similar |
| Memory Provider | ~300 lines | ~350 lines | ~80% logic similar |
| Embedding Provider | In CosmosUtils | In SQLiteAgentMemory | Fully duplicated |

---

## 2. Target Architecture

### 2.1 Unified File Structure

```
memory/
├── db/                              # Database abstraction layer
│   ├── __init__.py                  # Exports
│   ├── base.py                      # Abstract MemoryDatabase interface
│   ├── sqlite_backend.py            # SQLite + sqlite-vec implementation
│   ├── cosmos_backend.py            # CosmosDB implementation
│   ├── postgres_backend.py          # PostgreSQL + pgvector (future)
│   └── factory.py                   # Factory + configuration
│
├── providers/                       # NEW: Shared providers
│   ├── __init__.py
│   ├── embedding.py                 # Unified embedding providers
│   └── llm.py                       # LLM client abstraction
│
├── core/                            # NEW: Backend-agnostic core
│   ├── __init__.py
│   ├── memory_keeper.py             # Working memory (refactored)
│   ├── fact_retrieval.py            # CFR (refactored)
│   └── reflection.py                # Reflection (refactored)
│
├── agent_memory.py                  # NEW: Unified AgentMemory class
├── orchestrator.py                  # NEW: Unified orchestrator
├── memory_provider.py               # NEW: Unified ContextProvider
├── config.py                        # Configuration (enhanced)
├── models.py                        # Data models (keep)
└── prompts.py                       # LLM prompts (keep)
```

### 2.2 Target Dependency Graph

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Target Architecture                           │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│                         AgentMemory                                  │
│                              │                                       │
│                              ▼                                       │
│                    MemoryOrchestrator                                │
│                              │                                       │
│           ┌──────────────────┼──────────────────┐                   │
│           ▼                  ▼                  ▼                   │
│    MemoryKeeper      FactRetrieval       Reflection                 │
│           │                  │                  │                   │
│           └──────────────────┼──────────────────┘                   │
│                              ▼                                       │
│                    MemoryDatabase (ABC)                              │
│                              │                                       │
│           ┌──────────────────┼──────────────────┐                   │
│           ▼                  ▼                  ▼                   │
│    SQLiteDatabase    CosmosDBDatabase    PostgreSQLDatabase         │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Refactoring Phases

### Phase 1: Consolidate Embedding Providers ✅ COMPLETED

**Goal:** Single source for embedding logic.

**Status:** Completed on January 27, 2026

**Changes Made:**
- Created `memory/providers/__init__.py` - Module exports
- Created `memory/providers/embedding.py` - Contains `EmbeddingProvider` protocol and `OpenAIEmbeddingProvider`
- Updated `memory/db/base.py` - Imports `EmbeddingProvider` from `memory.providers.embedding`
- Updated `memory/db/factory.py` - Re-exports `OpenAIEmbeddingProvider` for backward compatibility
- Updated `memory/sqlite_agent_memory.py` - Uses unified provider, requires `openai_client` or `embedding_provider`
- Updated `memory/sqlite_orchestrator.py` - Uses unified provider, requires `openai_client` or `embedding_provider`
- Updated `memory/sqlite_memory_provider.py` - Uses unified provider, requires `openai_client` or `embedding_provider`
- Updated all demos to remove `use_mock_embeddings` parameter

**Key Decision:** MockEmbeddingProvider was **eliminated** from production code. Real embeddings are now required.
- Tests can define their own mock if needed
- This ensures semantic search quality in all production usage

**Backward compatibility:**
```python
# memory/db/__init__.py and memory/db/factory.py
# Re-export OpenAIEmbeddingProvider for backward compatibility
from memory.providers.embedding import OpenAIEmbeddingProvider
```

---

### Phase 2: Refactor Core Components ✅ COMPLETED

**Goal:** Make `MemoryKeeper`, `FactRetrieval`, `Reflection` use `MemoryDatabase` instead of raw containers.

**Status:** Completed on January 27, 2026

**Changes Made:**
- Created `memory/core/__init__.py` - Module exports with backward compatibility aliases
- Created `memory/core/memory_keeper.py` - Database-agnostic MemoryKeeper using MemoryDatabase interface
- Created `memory/core/fact_retrieval.py` - Database-agnostic FactRetrieval using MemoryDatabase interface
- Created `memory/core/reflection.py` - Database-agnostic Reflection using MemoryDatabase interface

**Key Changes in Core Components:**

1. **MemoryKeeper** (`memory/core/memory_keeper.py`):
   - Uses `MemoryDatabase` instead of `ContainerProxy`
   - Uses `EmbeddingProvider` instead of `CosmosUtils`
   - Includes `MemoryConfig` dataclass for configuration
   - Includes `ConversationTurn`, `SessionInitContext` data classes
   - Includes `MetadataOutput`, `KeyTopicsOutput`, `CumulativeSummaryOutput` Pydantic models

2. **FactRetrieval** (`memory/core/fact_retrieval.py`):
   - Uses `MemoryDatabase.vector_search()` instead of `CosmosUtils.execute_hybrid_search()`
   - Uses `EmbeddingProvider.get_embedding()` for query embedding
   - Includes `FactRetrievalConfig` dataclass
   - Backward compatibility alias: `ContextualFactRetrieval = FactRetrieval`

3. **Reflection** (`memory/core/reflection.py`):
   - Uses `MemoryDatabase.query()` and `MemoryDatabase.upsert()` instead of container methods
   - Uses `EmbeddingProvider` for insight embeddings
   - Includes `ReflectionConfig` dataclass
   - All Pydantic models included: `SessionInsight`, `ComprehensiveSessionAnalysis`, etc.
   - Backward compatibility alias: `ReflectionProcess = Reflection`

**Before:**
```python
class CurrentMemoryKeeper:
    def __init__(self, ..., interactions_container: ContainerProxy, ...):
        self.interactions_container = interactions_container
```

**After:**
```python
class MemoryKeeper:
    def __init__(self, ..., database: MemoryDatabase, ...):
        self.database = database
    
    async def final_prune(self, ...):
        await self.database.upsert(ContainerType.INTERACTIONS, document)
```

**Files created:**
- `memory/core/memory_keeper.py` - Refactored from `current_memory_keeper.py`
- `memory/core/fact_retrieval.py` - Refactored from `fact_retrieval.py`
- `memory/core/reflection.py` - Refactored from `reflection.py`

---

### Phase 3: Create Unified Orchestrator ✅ COMPLETED

**Goal:** Single orchestrator that works with any backend.

**Status:** Completed on January 27, 2026

**Changes Made:**
- Created `memory/core/orchestrator.py` - Unified MemoryOrchestrator (~500 lines)
- Updated `memory/core/__init__.py` - Added orchestrator exports

**Key Features:**
- Uses `MemoryDatabase` abstraction layer
- Uses new core components: `MemoryKeeper`, `FactRetrieval`, `Reflection`
- Supports SQLite and CosmosDB through `db_type` parameter
- `OrchestratorConfig` dataclass for configuration
- `create_orchestrator()` factory function
- Backward compatibility aliases: `MemoryServiceOrchestrator`, `SQLiteMemoryOrchestrator`

**Previous state:**
- `MemoryServiceOrchestrator` (767 lines) - CosmosDB-specific
- `SQLiteMemoryOrchestrator` (717 lines) - SQLite-specific

**New unified API:**
```python
from memory.core import MemoryOrchestrator, create_orchestrator
from memory.db.factory import DatabaseType

# With SQLite (default)
orchestrator = MemoryOrchestrator(
    user_id="user123",
    openai_client=openai_client,
    db_type=DatabaseType.SQLITE,
    db_path="memory.db"
)

# With CosmosDB
orchestrator = MemoryOrchestrator(
    user_id="user123",
    openai_client=openai_client,
    db_type=DatabaseType.COSMOSDB,
    connection_string="..."
)

# Using factory function
orchestrator = create_orchestrator(
    user_id="user123",
    db_type=DatabaseType.SQLITE,
    openai_client=openai_client
)

# Usage
async with orchestrator:
    await orchestrator.start_session()
    await orchestrator.process_turn("Hello", "Hi there!")
    context = await orchestrator.get_current_context()
    result = await orchestrator.end_session()
```

---

### Phase 4: Create Unified AgentMemory ✅ COMPLETED

**Goal:** Single high-level API class.

**Status:** Completed on January 27, 2026

**Changes Made:**
- Created `memory/core/agent_memory.py` - Unified AgentMemory class
- Updated `memory/core/__init__.py` - Added AgentMemory exports
- Updated `memory/__init__.py` - Added new unified API exports

**Key Features:**
- `AgentMemory` class - high-level interface wrapping `MemoryOrchestrator`
- `AgentMemoryConfig` dataclass - simplified configuration
- `create_agent_memory()` factory function
- Database-agnostic: supports SQLite (default) and CosmosDB via `db_type` parameter
- Backward compatibility aliases: `CosmosAgentMemory`, `SQLiteAgentMemory`

**Previous state:**
- `CosmosAgentMemory` (426 lines) - CosmosDB-specific
- `SQLiteAgentMemory` (663 lines) - SQLite-specific

**New unified API:**
```python
from memory import AgentMemory, AgentMemoryConfig, create_agent_memory
from memory.db.factory import DatabaseType

# SQLite (default, simplest usage)
memory = AgentMemory(
    user_id="user123",
    openai_client=openai_client,
    db_path="memory.db"
)

# CosmosDB (enterprise)
memory = AgentMemory(
    user_id="user123",
    openai_client=openai_client,
    db_type=DatabaseType.COSMOSDB,
    connection_string=os.getenv("COSMOS_CONNECTION_STRING")
)

# Using factory function
memory = create_agent_memory(
    user_id="user123",
    db_type=DatabaseType.SQLITE,
    openai_client=openai_client
)

# Context manager usage
async with AgentMemory(user_id="user123", openai_client=client) as memory:
    await memory.add_turn("What's a Roth IRA?", "A Roth IRA is...")
    context = memory.get_context()

# Manual session management
memory = AgentMemory(user_id="user123", openai_client=client)
await memory.start_session()
await memory.add_turn("Hello", "Hi there!")
context = memory.get_context()
facts = await memory.search("retirement plans")
await memory.end_session()
```

**Methods Available:**
- `start_session()` - Start a new session
- `add_turn(user_message, assistant_message)` - Add conversation turn
- `end_session()` - End session with reflection
- `get_context()` - Get formatted memory context for prompts
- `search(query)` - Search memory for relevant facts
- `get_insights(category=None)` - Get stored user insights
- `get_sessions(limit=10)` - Get recent session summaries
- `get_status()` - Get current memory status

---

### Phase 5: Update Demos and Examples ✅ COMPLETED

**Goal:** Update demos to use the new unified API.

**Status:** Completed on January 27, 2026

**Changes Made:**
- Created `demos/quickstart/unified_usage.py` - New unified API quickstart demo
- Created `demos/scenarios/financial_advisor_unified.py` - Unified financial advisor scenario
- Updated `demos/README.md` - Added unified API documentation and examples

**New Demo Files:**

1. **`demos/quickstart/unified_usage.py`** - Comprehensive unified API demo:
   - Example 1: SQLite backend (default)
   - Example 2: Context manager usage
   - Example 3: Factory function
   - Example 4: CosmosDB backend
   - Example 5: Custom configuration

2. **`demos/scenarios/financial_advisor_unified.py`** - Multi-session scenario:
   - Uses unified `AgentMemory` API
   - Same code works with SQLite or CosmosDB
   - Shows memory retention across 3 sessions

**Usage:**
```bash
# Run unified API quickstart
uv run python demos/quickstart/unified_usage.py

# Run unified financial advisor scenario
uv run python demos/scenarios/financial_advisor_unified.py
```

**Notes:**
- Legacy demos (`*_sqlite.py`, `*_cosmos.py`) remain for backward compatibility
- New demos use `from memory import AgentMemory` pattern
- MemoryContextProvider unification deferred to Phase 6

---

### Phase 6: Cleanup & Migration ✅ COMPLETED

**Goal:** Mark deprecated files and provide migration path.

**Status:** Completed on January 27, 2026

**Approach:** Rather than deleting files immediately, deprecation warnings were added
to ensure backward compatibility while guiding users to the new unified API.

**Files Deprecated (with warnings):**

| Old File | Replacement | Warning Added |
|----------|-------------|---------------|
| `cosmos_agent_memory.py` | `memory.core.agent_memory.AgentMemory` | ✅ |
| `sqlite_agent_memory.py` | `memory.core.agent_memory.AgentMemory` | ✅ |
| `orchestrator.py` | `memory.core.orchestrator.MemoryOrchestrator` | ✅ |
| `sqlite_orchestrator.py` | `memory.core.orchestrator.MemoryOrchestrator` | ✅ |
| `cosmos_utils.py` | `memory.providers.embedding` + `memory.db` | ✅ |
| `current_memory_keeper.py` | `memory.core.memory_keeper.MemoryKeeper` | ✅ |
| `fact_retrieval.py` | `memory.core.fact_retrieval.FactRetrieval` | ✅ |
| `reflection.py` | `memory.core.reflection.Reflection` | ✅ |

**Files Retained (still needed):**
- `cosmos_memory_provider.py` - Still used for Agent Framework integration
- `sqlite_memory_provider.py` - Still used for Agent Framework integration
- `db/adapters.py` - Still used by legacy orchestrators
- `config.py` - Still used by new and old code
- `models.py` - Shared data models
- `prompts.py` - LLM prompt templates

**Migration Guide:**

```python
# OLD (deprecated, will emit warning)
from memory import CosmosAgentMemory
memory = CosmosAgentMemory(user_id="user123", cosmos_connection_string=conn, ...)

# NEW (recommended)
from memory import AgentMemory
from memory.db.factory import DatabaseType
memory = AgentMemory(
    user_id="user123",
    db_type=DatabaseType.COSMOSDB,
    connection_string=conn,
    openai_client=client
)
```

**Deprecation Timeline:**
- v0.2.0: Deprecation warnings added (current)
- v0.3.0: Remove deprecated files (future)

---

## 4. Interface Definitions

### 4.1 Unified AgentMemory Interface

```python
class AgentMemory:
    """High-level agent memory API."""
    
    # Lifecycle
    async def initialize(self) -> None: ...
    async def close(self) -> None: ...
    async def __aenter__(self) -> "AgentMemory": ...
    async def __aexit__(self, ...): ...
    
    # Session management
    async def start_session(self, session_id: Optional[str] = None) -> str: ...
    async def end_session(self) -> Dict[str, Any]: ...
    async def restore_session(self, session_id: str) -> Dict[str, Any]: ...
    
    # Turn processing
    async def add_turn(self, user_message: str, assistant_message: str) -> None: ...
    async def process_turn(self, user_message: str, assistant_message: str) -> None: ...
    
    # Context retrieval
    def get_context(self) -> str: ...
    async def retrieve_facts(self, query: str, top_k: int = 5) -> str: ...
    async def get_user_profile(self) -> Dict[str, Any]: ...
    
    # Search
    async def search_interactions(self, query: str, top_k: int = 5) -> List[Dict]: ...
    async def search_insights(self, query: str, top_k: int = 5) -> List[Dict]: ...
    async def search_sessions(self, query: str, top_k: int = 5) -> List[Dict]: ...
    
    # Properties
    @property
    def user_id(self) -> str: ...
    @property
    def session_id(self) -> Optional[str]: ...
    @property
    def database_type(self) -> DatabaseType: ...
```

### 4.2 Unified Orchestrator Interface

```python
class MemoryOrchestrator:
    """Coordinates memory operations across components."""
    
    # Lifecycle
    async def initialize(self) -> None: ...
    async def close(self) -> None: ...
    
    # Session
    async def initialize_session(self) -> Dict[str, Any]: ...
    async def end_session(self) -> Dict[str, Any]: ...
    
    # Turn processing
    async def process_turn(self, user_msg: str, assistant_msg: str) -> None: ...
    
    # Context
    def get_working_context(self) -> str: ...
    async def retrieve_facts(self, query: str, top_k: int = 5) -> str: ...
    
    # Auto-enrichment
    async def get_enriched_context(self, ...) -> str: ...
    
    # Properties
    @property
    def turn_count(self) -> int: ...
```

---

## 5. Migration Path

### 5.1 Backward Compatibility Strategy

1. **Keep old class names as aliases** for 1-2 release cycles
2. **Add deprecation warnings** when old classes are used
3. **Update documentation** to point to new unified classes
4. **Update demos** to use new classes
5. **Remove aliases** after deprecation period

### 5.2 Demo Updates Required

| Demo | Current | After Refactor |
|------|---------|----------------|
| Financial Advisor CosmosDB | `CosmosAgentMemory` | `AgentMemory(db_type=DatabaseType.COSMOSDB)` |
| Financial Advisor SQLite | `SQLiteAgentMemory` | `AgentMemory(db_type=DatabaseType.SQLITE)` |
| Hidden Tool | `CosmosMemoryProvider` | `MemoryContextProvider` |
| Interactive Demo | `SQLiteMemoryOrchestrator` | `MemoryOrchestrator(db_type=...)` |

---

## 6. Testing Strategy

### 6.1 Unit Tests

- Test each component works with both SQLite and CosmosDB backends
- Use dependency injection to mock database
- Test backward compatibility aliases

### 6.2 Integration Tests

```python
@pytest.mark.parametrize("db_type", [DatabaseType.SQLITE, DatabaseType.COSMOSDB])
async def test_full_session_lifecycle(db_type):
    memory = AgentMemory(user_id="test", db_type=db_type, ...)
    async with memory:
        await memory.start_session()
        await memory.add_turn("Hello", "Hi there!")
        context = memory.get_context()
        assert "Hello" in context
        await memory.end_session()
```

### 6.3 Parity Tests

Ensure identical behavior between backends:
- Same inputs produce equivalent outputs
- Same search queries return similar results
- Session lifecycle behaves identically

---

## 7. Effort Estimation

| Phase | Effort | Priority |
|-------|--------|----------|
| Phase 1: Embedding Providers | 2-4 hours | High |
| Phase 2: Core Components | 4-8 hours | High |
| Phase 3: Unified Orchestrator | 8-12 hours | High |
| Phase 4: Unified AgentMemory | 4-6 hours | High |
| Phase 5: Unified Provider | 4-6 hours | Medium |
| Phase 6: Cleanup | 4-6 hours | Low |
| Testing & Validation | 8-12 hours | High |

**Total Estimated Effort:** 34-54 hours (4-7 days)

---

## 8. Success Criteria

1. ✅ Single `AgentMemory` class works with both SQLite and CosmosDB
2. ✅ No duplicate orchestrator implementations
3. ✅ All demos work with unified classes
4. ✅ Backend selection via configuration or parameter
5. ✅ Backward compatibility maintained for existing code
6. ✅ PostgreSQL backend can be added without changing core code
7. ✅ Test coverage >80% for unified components

---

## 9. Future Extensibility

### Adding PostgreSQL Backend

1. Create `memory/db/postgres_backend.py`
2. Implement `PostgreSQLDatabase(MemoryDatabase)`
3. Add `DatabaseType.POSTGRESQL` to factory
4. Done! No changes to orchestrator, memory, or demos needed.

### Adding New Container Type

1. Add to `ContainerType` enum
2. Add schema to each backend
3. Core components automatically support it

---

## Appendix A: Key Code Changes

### A.1 Current MemoryKeeper Constructor

```python
# BEFORE: current_memory_keeper.py
class CurrentMemoryKeeper:
    def __init__(
        self,
        user_id: str,
        session_id: str,
        interactions_container: ContainerProxy,  # CosmosDB-specific!
        summaries_container: ContainerProxy,     # CosmosDB-specific!
        insights_container: ContainerProxy,      # CosmosDB-specific!
        cosmos_utils: CosmosUtils,               # CosmosDB-specific!
        chat_client: AzureOpenAI,
        config: MemoryConfig
    ):
```

### A.2 Refactored MemoryKeeper Constructor

```python
# AFTER: core/memory_keeper.py
class MemoryKeeper:
    def __init__(
        self,
        user_id: str,
        session_id: str,
        database: MemoryDatabase,        # Abstract - works with any backend!
        embedding_provider: EmbeddingProvider,
        chat_client,
        config: MemoryConfig
    ):
```

---

## Appendix B: Files to Create

1. `memory/providers/__init__.py`
2. `memory/providers/embedding.py`
3. `memory/core/__init__.py`
4. `memory/core/memory_keeper.py`
5. `memory/core/fact_retrieval.py`
6. `memory/core/reflection.py`
7. `memory/agent_memory.py` (unified)
8. `memory/orchestrator_unified.py` → rename to `orchestrator.py`
9. `memory/memory_provider.py` (unified)

---

## Appendix C: Files to Retire (After Migration)

1. `memory/cosmos_agent_memory.py`
2. `memory/sqlite_agent_memory.py`
3. `memory/sqlite_orchestrator.py`
4. `memory/cosmos_memory_provider.py`
5. `memory/sqlite_memory_provider.py`
6. `memory/cosmos_utils.py`
7. `memory/current_memory_keeper.py`
8. `memory/db/adapters.py`
