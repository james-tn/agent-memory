# 🏗️ Agent Memory Service - Implementation Design

---

## 1. Executive Summary

This document outlines the implementation design for the **Agent Memory Service**, integrating with **Microsoft Agent Framework** and **Azure CosmosDB** as the vector database backend. The service provides agents with human-like memory capabilities for personalized, context-aware interactions across sessions.

---

## 2. Inspiration from Human Memory

The design is inspired by how humans manage memory and learning:

- **Active vs. Long-Term Memory:**  
  Humans keep only key details in short-term (active) memory while storing the rest in long-term memory or external aids. When needed, they retrieve details using associative recall.

- **Reflection and Learning:**  
  After interactions, humans naturally reflect on events, extracting key insights and lessons learned to store for future use.

- **Recency, Frequency, and Importance:** *(Planned - not yet implemented)*  
  Recent and frequently encountered information would be prioritized in active memory. Information deemed important through reflection would be retained longer or recalled more easily. Currently, retrieval uses vector similarity only; recency/frequency boosts are a future enhancement.

---

## 3. Architecture Overview

### 3.1 Technology Stack

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Agent Framework** | Microsoft Agent Framework (v1.0.0b251016) | Core agent orchestration |
| **LLM Provider** | Azure OpenAI (configurable via env vars) | Chat completion & reasoning |
| **Embedding Model** | Azure OpenAI (text-embedding-3-large) | Vector embeddings generation |
| **Database Backend** | SQLite (default), CosmosDB, or PostgreSQL | Memory storage & retrieval |
| **Vector Search** | sqlite-vec, CosmosDB VectorDistance, or pgvector | Semantic similarity search |
| **Authentication** | Azure Service Principal (for cloud backends) | CosmosDB & OpenAI access |
| **Language** | Python 3.12+ | Implementation |

### 3.2 System Components

```
┌─────────────────────────────────────────────────────────────┐
│                     Your AI Agent                            │
│         Microsoft Agent Framework + ContextProvider          │
│  context_providers=[CosmosMemoryProvider]                   │
└────────────────┬────────────────────────────────────────────┘
                 │
                 │  (Remote mode: HTTP)  OR  (Embedded mode: Direct)
                 │
    ┌────────────▼──────────────────────────────────────────┐
    │         FastAPI Memory Service (Port 8000)            │
    │                                                        │
    │  • Session Pool (LRU Cache)  - Configurable size/TTL  │
    │  • Background Eviction       - Periodic cleanup        │
    │  • Health & Monitoring       - /health, /stats         │
    │                                                        │
    └────────────┬──────────────────────────────────────────┘
                 │
    ┌────────────▼──────────────┐         ┌─────────────────────────┐
    │  Memory Orchestrator      │         │  Azure OpenAI Service   │
    │                           │         │                         │
    │  ┌────────────────────┐   │         │  • REASONING_MODEL      │
    │  │ Current Memory     │   │         │    (gpt-4o, gpt-5)      │
    │  │ Keeper             │   │         │  • PROCESSING_MODEL     │
    │  │ (k-turn buffer)    │   │         │    (gpt-4o-mini)        │
    │  └────────────────────┘   │         │  • EMB_DEPLOYMENT       │
    │  ┌────────────────────┐   │         │    (text-embedding-3)   │
    │  │ CFR Agent          │◄──┼───┐     └─────────────────────────┘
    │  │ (REASONING_MODEL)  │   │   │
    │  │ Tools:             │   │   │ Hidden tool injection
    │  │ • search_interact. │   │   │ (recall_facts)
    │  │ • search_insights  │   │   │
    │  │ • search_summaries │   │   │
    │  └────────────────────┘   │   │
    │  ┌────────────────────┐   │   │
    │  │ Reflection Process │   │   │
    │  │ • Session reflect. │   │   │
    │  │ • Auto long-term   │◄──┼───┘ Every N sessions
    │  └────────────────────┘   │
    └────────────┬──────────────┘
                 │
    ┌────────────▼──────────────┐
    │   Database Backend        │
    │   (Abstraction Layer)     │
    │                           │
    │  Options:                 │
    │  • SQLite + sqlite-vec    │  ← Default (no server)
    │  • Azure CosmosDB NoSQL   │  ← Enterprise (hybrid search)
    │  • PostgreSQL + pgvector  │  ← Future
    │                           │
    │  Tables/Containers:       │
    │  • interactions           │  ← Conversation chunks (k-turn)
    │  • session_summaries      │  ← Session metadata + summaries
    │  • insights               │  ← Session + long-term insights
    │                           │
    └───────────────────────────┘
```

---

## 4. CosmosDB Schema Design

### 4.1 Database: `agent_memory_db`

#### Container 1: `interactions`
Stores multi-turn conversation chunks with vector embeddings for semantic search.

**Partition Key:** `/user_id`

**Document Schema:**
```json
{
  "id": "uuid-string",
  "user_id": "user123",
  "session_id": "session-uuid",
  "timestamp": "2025-10-22T10:30:00Z",
  "content": "user: What are my investment options for retirement?\nassistant: Based on your age and goals, I recommend considering both traditional and Roth IRAs...\nuser: How much should I contribute?\nassistant: A good rule of thumb is to contribute at least 15% of your income...",
  "content_vector": [0.123, -0.456, ...],
  "summary": "User inquired about retirement investment options and contribution recommendations. Discussed IRA types and contribution percentages.",
  "summary_vector": [0.789, -0.234, ...],
  "metadata": {
    "mentioned_topics": ["retirement", "IRA", "contribution"],
    "entities": ["traditional IRA", "Roth IRA", "401k"]
  },
  "_ts": 1729591800
}
```

**Vector Indexing Policy:**
```python
{
  "vectorEmbeddings": [
    {
      "path": "/content_vector",
      "dataType": "float32",
      "distanceFunction": "cosine",
      "dimensions": 1536
    },
    {
      "path": "/summary_vector",
      "dataType": "float32",
      "distanceFunction": "cosine",
      "dimensions": 1536
    }
  ]
}
```

**Full-Text Policy:**
```python
{
  "defaultLanguage": "en-US",
  "fullTextPaths": [
    {"path": "/content", "language": "en-US"},
    {"path": "/metadata/mentioned_topics", "language": "en-US"},
    {"path": "/metadata/entities", "language": "en-US"}
  ]
}
```

**Note:** Each document contains k turns (configurable buffer size). When the memory keeper accumulates k turns, they are flattened into a single document with content in format: `user: ...\nassistant: ...\nuser: ...`. The summary, mentioned_topics, and entities are generated using `AZURE_OPENAI_CHAT_MINI_DEPLOYMENT`.

#### Container 2: `insights`
Stores extracted insights at two levels: session-based and long-term aggregated.

**Partition Key:** `/user_id`

**Session Insight Document Schema:**
```json
{
  "id": "insight-uuid",
  "user_id": "user123",
  "insight_type": "session",
  "session_ids": ["session-uuid-1", "session-uuid-2"],
  "insight_text": "User expressed concern about market volatility affecting retirement plans. Discussed risk mitigation strategies including diversification.",
  "insight_vector": [0.789, -0.234, ...],
  "confidence": 0.85,
  "importance": "high",
  "category": "concern",
  "reflection_flag": "insight",
  "processed": false,
  "created_at": "2025-10-22T10:30:00Z",
  "updated_at": "2025-10-22T10:30:00Z"
}
```

**Long-term Insight Document Schema:**
```json
{
  "id": "longterm-{user_id}",
  "user_id": "user123",
  "insight_type": "long_term",
  "insight_text": "Client profile: 35-year-old married professional planning retirement at 65. Moderate risk tolerance with focus on balanced growth. Primary goals: maximize 401k contributions, diversify investments, and build emergency fund. Key concerns: market volatility and insufficient retirement savings. Prefers quarterly reviews and data-driven recommendations.",
  "insight_vector": [0.456, -0.789, ...],
  "confidence": null,
  "importance": null,
  "category": null,
  "source_insight_ids": ["insight-1", "insight-2", "insight-3"],
  "created_at": "2025-10-15T08:00:00Z",
  "updated_at": "2025-10-22T10:30:00Z"
}
```

**Notes:**
- **Session insights**: Generated at the end of each session. Can span multiple sessions if the reflection process aggregates related sessions. The `reflection_flag` can be "insight" (significant insights found) or "no-insight" (trivial session). Sessions with "no-insight" are kept for future aggregation.
- **Long-term insight**: One single document per user that aggregates all processed session insights into a comprehensive user profile. **Automatically updated every N sessions** (default: 5) via `longterm_synthesis_frequency` config.
- **processed** field: Marks whether a session insight has been incorporated into long-term reflection.
- **category**: Defined by reflection prompt (e.g., "demographics", "financial_goals", "risk_profile", "concern", "preference")

#### Container 3: `session_summaries`
Stores session-level metadata and summaries for quick context loading and reflection tracking.

**Partition Key:** `/user_id`

**Document Schema:**
```json
{
  "id": "session-uuid",
  "user_id": "user123",
  "start_time": "2025-10-22T10:00:00Z",
  "end_time": "2025-10-22T11:30:00Z",
  "summary": "User inquired about retirement planning strategies, discussed 401k contribution limits, and reviewed risk assessment results.",
  "summary_vector": [0.456, -0.789, ...],
  "key_topics": ["retirement", "401k", "risk assessment"],
  "extracted_insights": ["insight-uuid-1", "insight-uuid-2"],
  "status": "active|completed",
  "reflection_status": "pending|no-insight|processed"
}
```

**Notes:**
- **status**: "active" = session ongoing, "completed" = session ended
- **reflection_status**: 
  - "pending" = awaiting session reflection
  - "no-insight" = reflection ran but found no significant insights (kept for future aggregation)
  - "processed" = insights extracted and incorporated
- The summary is generated at session end and used for initializing future sessions with recent context

---

## 5. Core Service Components

### 5.1 Memory Orchestrator (`orchestrator.py`)

**Class: `MemoryServiceOrchestrator`**

```python
class MemoryServiceOrchestrator:
    """
    Main orchestration layer for Agent Memory Service.
    Coordinates CurrentMemoryKeeper, CFR Agent, and ReflectionProcess.
    """
    
    def __init__(
        self,
        user_id: str,
        cosmos_client: CosmosClient,
        chat_client: AzureOpenAI,  # For gpt-5-nano and gpt-5-nanoo-mini
        embedding_client: AzureOpenAI,
        config: MemoryConfig = None
    ):
        self.user_id = user_id
        self.config = config or MemoryConfig()
        
        # CosmosDB setup
        self.db = cosmos_client.get_database_client(self.config.COSMOS_DB_NAME)
        self.interactions_container = self.db.get_container_client(
            self.config.INTERACTIONS_CONTAINER
        )
        self.insights_container = self.db.get_container_client(
            self.config.INSIGHTS_CONTAINER
        )
        self.summaries_container = self.db.get_container_client(
            self.config.SUMMARIES_CONTAINER
        )
        
        # Initialize components
        self.memory_keeper = CurrentMemoryKeeper(
            user_id=user_id,
            interactions_container=self.interactions_container,
            summaries_container=self.summaries_container,
            insights_container=self.insights_container,
            chat_client=chat_client,
            embedding_client=embedding_client,
            config=self.config
        )
        
        self.cfr_agent = ContextualFactRetrievalAgent(
            interactions_container=self.interactions_container,
            insights_container=self.insights_container,
            summaries_container=self.summaries_container,
            chat_client=chat_client,
            embedding_client=embedding_client,
            config=self.config
        )
        
        self.reflection = ReflectionProcess(
            insights_container=self.insights_container,
            summaries_container=self.summaries_container,
            interactions_container=self.interactions_container,
            chat_client=chat_client,
            config=self.config
        )
    
    async def initialize_session(self, session_id: str) -> str:
        """
        Load context for new session.
        Returns formatted session initialization block.
        """
        return await self.memory_keeper.initialize_session_context()
    
    async def add_turn(self, session_id: str, role: str, content: str) -> None:
        """Add a conversation turn to the buffer."""
        await self.memory_keeper.add_turn(session_id, role, content)
    
    async def get_current_context(self) -> str:
        """Get formatted context (init block + summary + active turns)."""
        return self.memory_keeper.get_current_context()
    
    async def retrieve_facts(self, query: str) -> str:
        """
        Call CFR mini-agent to retrieve relevant facts.
        This is exposed as a tool to the main agent.
        """
        return await self.cfr_agent.retrieve_facts(query)
    
    async def end_session(self, session_id: str) -> dict:
        """
        End session:
        1. Prune any remaining turns
        2. Create session summary
        3. Run session reflection
        """
        # Prune remaining turns
        await self.memory_keeper.final_prune(session_id)
        
        # Create session summary
        summary = await self.memory_keeper.create_session_summary(session_id)
        
        # Run reflection
        insights = await self.reflection.reflect_on_session(session_id)
        
        return {
            "session_summary": summary,
            "insights": insights
        }
    
    async def run_longterm_reflection(self) -> dict:
        """Manually trigger long-term reflection (admin/maintenance)."""
        return await self.reflection.run_longterm_reflection(self.user_id)
```

### 4.2 Current Memory Keeper (`current_memory_keeper.py`)

**Responsibilities:**
- Maintain k-turn buffer before triggering pruning/summarization
- Keep last N active turns in context (configurable, default 5)
- Manage cumulative conversation summary
- Build structured context with session initialization block

**Context Structure:**
```
[System Message] ← Set by agent developer

<session_initialization>
### Key Insights
[Long-term insight text loaded at session start]

### Recent Session Summaries
- At 12:00 PM, Dec 04, 2024: Discussed 401k rollover options and tax implications
- At 01:00 PM, Dec 06, 2024: Reviewed risk assessment and portfolio allocation
</session_initialization>

### Conversation Summary
[Cumulative summary: updated every k turns by combining old summary + new k turns]

### Active Conversation
user: What's my current allocation?
assistant: Your current allocation is 60% stocks, 30% bonds, 10% cash...
user: Should I rebalance?
assistant: Based on your risk profile...
[... last N turns]
```

**Key Methods:**
- `initialize_session_context(user_id: str) -> str`: Load long-term insights + recent session summaries
- `get_current_context() -> str`: Return formatted context (init block + summary + active turns)
- `add_turn(role: str, content: str)`: Add turn to buffer
- `maybe_prune() -> Optional[dict]`: When buffer reaches k turns, summarize and create interaction document
- `update_cumulative_summary(old_summary: str, new_turns: list) -> str`: Generate new cumulative summary

**Configuration:**
- `k` (buffer size before pruning): Default 10 turns
- `N` (active turns to keep): Default 5 turns

### 4.3 Contextual Fact Retrieval (`fact_retrieval.py`)

**Architecture:** Mini-agent using `AZURE_OPENAI_CHAT_MINI_DEPLOYMENT` with tools to search memory.

**Responsibilities:**
- Act as intelligent retrieval agent that reasons about search strategy
- Decide which containers to search (interactions, insights, or both)
- Synthesize and compile search results into coherent facts
- Return formatted results to main agent

**Agent Tools:**
1. `search_interactions(query: str, top_k: int = 5) -> list[dict]`
   - Vector + full-text hybrid search on interactions container
   - Search across content, summary, topics, entities
   
2. `search_insights(query: str, insight_type: str = None, top_k: int = 5) -> list[dict]`
   - Vector search on insights container
   - Optional filter by insight_type (session/long_term)
   
3. `search_session_summaries(query: str, top_k: int = 3) -> list[dict]`
   - Vector search on session summaries
   - Useful for temporal context

**Workflow:**
1. Main agent calls CFR agent via tool: "Find information about user's 401k discussions"
2. CFR agent reasons: "I should search interactions for detailed conversation and insights for extracted facts"
3. CFR agent calls its tools: `search_interactions(...)` and `search_insights(...)`
4. CFR agent synthesizes results: "User discussed 401k rollover in 3 sessions. Key facts: ..."
5. Returns compiled facts to main agent

**Key Methods:**
- `retrieve_facts(query: str) -> str`: Main entry point (agent decides search strategy)
- `_format_results(results: list[dict]) -> str`: Format search results for readability

### 4.4 CosmosDB Utilities (`cosmos_utils.py`)

**Responsibilities:**
- Common utility functions for CosmosDB operations
- Embedding generation and vectorization
- Query helpers for vector and hybrid search

**Key Utility Functions:**
- `get_embedding(text: str, client: AzureOpenAI) -> list[float]`: Generate embedding vector
- `execute_vector_search(container, query_embedding: list[float], top_k: int, filters: dict = None) -> list[dict]`
- `execute_hybrid_search(container, text: str, embedding: list[float], top_k: int) -> list[dict]`
- `upsert_document(container, document: dict) -> str`
- `batch_upsert_documents(container, documents: list[dict]) -> list[str]`

**Note:** This replaces "Raw Memory Index" - it's now a collection of utility functions rather than a separate component, as the interactions container is directly accessed by other components.

### 4.5 Reflection Process (`reflection.py`)

**Responsibilities:**
- Extract insights from completed sessions (session-based reflection)
- Aggregate session insights into long-term user profile (long-term reflection)
- Determine insight importance, confidence, and categories
- Handle "no-insight" sessions for future aggregation

**Two Reflection Modes:**

#### A) Session-Based Reflection
Runs at the end of each session (or on-demand for pending sessions).

**Process:**
1. Retrieve all interactions for the session(s)
2. Call LLM (using `AZURE_OPENAI_REASONING_MODEL`) with extraction prompt
3. LLM outputs:
   - `reflection_flag`: "insight" or "no-insight"
   - If "insight": array of insights with category, importance, confidence
   - If "no-insight": empty array
4. Store session insights in `insights` container with `processed=false`
5. Update `session_summaries` with `reflection_status`:
   - "processed" if insights generated
   - "no-insight" if no significant insights (kept for future aggregation)

**Key Methods:**
- `reflect_on_session(session_id: str) -> list[dict]`: Run reflection on single session
- `reflect_on_multiple_sessions(session_ids: list[str]) -> list[dict]`: Aggregate multiple "no-insight" sessions
- `extract_session_insights(conversations: str) -> dict`: Call LLM with extraction prompt

#### B) Long-term Reflection
Manually triggered to update the user's overall profile.

**Process:**
1. Retrieve all unprocessed session insights (`processed=false`)
2. Retrieve current long-term insight document
3. Call LLM to synthesize: baseline long-term insight + new session insights
4. Update long-term insight document
5. Mark session insights as `processed=true`

**Key Methods:**
- `run_longterm_reflection(user_id: str) -> dict`: Update long-term insight
- `synthesize_longterm_insight(baseline: str, new_insights: list[dict]) -> str`: LLM synthesis

---

## 5. Integration with Microsoft Agent Framework

### 5.1 Memory-Aware Agent Wrapper

```python
class MemoryAwareAgent:
    """
    Wraps Microsoft Agent Framework ChatAgent with memory capabilities.
    """
    
    def __init__(
        self,
        chat_agent: ChatAgent,
        memory_service: AgentMemoryService,
        session_id: str
    ):
        self.agent = chat_agent
        self.memory = memory_service
        self.session_id = session_id
        self.turn_counter = 0
    
    async def run(self, user_message: str, thread: AgentThread) -> str:
        """
        Enhanced run method with memory operations:
        1. Store user message in memory
        2. Retrieve relevant facts (if needed)
        3. Inject facts into context
        4. Call agent
        5. Store assistant response
        6. Check if summarization needed
        """
        # Store user message
        await self.memory.store_interaction(
            session_id=self.session_id,
            role="user",
            content=user_message
        )
        
        # Retrieve relevant context
        relevant_facts = await self.memory.retrieve_relevant_facts(
            query=user_message,
            top_k=3
        )
        
        # Enhance prompt with facts
        enhanced_message = self._inject_facts(user_message, relevant_facts)
        
        # Run agent
        result = await self.agent.run(enhanced_message, thread=thread)
        
        # Store response
        await self.memory.store_interaction(
            session_id=self.session_id,
            role="assistant",
            content=result.text
        )
        
        # Check compression
        summary = await self.memory.current_memory_keeper.maybe_summarize()
        
        self.turn_counter += 1
        return result.text
    
    async def end_session(self):
        """Trigger reflection at session end."""
        insights = await self.memory.reflect_on_session(self.session_id)
        return insights
```

### 5.2 Memory Retrieval as Agent Tool

```python
def create_memory_retrieval_tool(memory_service: AgentMemoryService):
    """
    Create a callable tool for the agent to explicitly query memory.
    """
    
    async def retrieve_user_facts(
        query: Annotated[str, Field(description="What to search for in memory")]
    ) -> str:
        """Retrieve relevant facts about the user from long-term memory."""
        facts = await memory_service.retrieve_relevant_facts(query, top_k=5)
        
        if not facts:
            return "No relevant information found in memory."
        
        result = "Relevant information from memory:\n"
        for i, fact in enumerate(facts, 1):
            result += f"{i}. {fact['insight_text']} (confidence: {fact.get('confidence', 'N/A')})\n"
        
        return result
    
    return retrieve_user_facts
```

---

## 6. Demo Scenarios

### 6.1 Scenario 1: Long Context Conversation with Memory Retrieval

**Setup:**
- Pre-populate 20+ interactions about user's financial situation
- Simulate a new session where user asks: "What did we discuss about my 401k?"

**Expected Behavior:**
- Agent retrieves relevant past interactions via semantic search
- Agent provides contextual answer referencing previous discussions
- No need to keep all 20+ turns in active context

**Demo Script:**
```python
# 1. Setup: Index historical data
# 2. Start new session
# 3. User query triggers memory retrieval
# 4. Agent responds with historical context
```

### 6.2 Scenario 2: Reflection-Powered Session Initialization

**Setup:**
- Pre-create multiple completed sessions with insights extracted
- Start fresh session with no recent history

**Expected Behavior:**
- Agent loads relevant insights at startup
- Agent greets user with personalized context
- Example: "Welcome back! Last time we were discussing your retirement plan for 2040..."

**Demo Script:**
```python
# 1. Pre-create insights: user profile, goals, preferences
# 2. Initialize new session → loads insights
# 3. Agent proactively mentions relevant context
```

### 6.3 Scenario 3: Real-time Context Compression

**Setup:**
- Simulate extended conversation (15+ turns)
- Monitor memory compression in action

**Expected Behavior:**
- First 10 turns stored verbatim
- Older turns summarized when threshold reached
- Recent 5 turns + summary maintained in active context

---

## 7. Configuration Parameters

```python
# config.py

@dataclass
class MemoryConfig:
    # Current Memory Keeper
    buffer_size: int = 10  # Turns before summarization (K_TURN_BUFFER)
    active_turns: int = 5  # Recent turns in context (N_ACTIVE_TURNS)
    num_recent_sessions_for_init: int = 2  # Recent session summaries to load
    
    # Fact Retrieval
    retrieval_mode: str = "on-demand"  # Agent calls CFR via tool
    top_k_results: int = 5
    similarity_threshold: float = 0.75
    
    # Auto-Enrichment (Keyword-triggered memory search)
    auto_enrich_context: bool = False  # Enable automatic memory search
    enrichment_trigger_keywords: List[str] = [  # Keywords that trigger search
        "remember", "recall", "previous", "last time", "before",
        "allergy", "allergies", "medication", "prescribe",
        "history", "past", "earlier", "mentioned"
    ]
    
    # Session Management
    auto_manage_sessions: bool = True  # Auto-end sessions in __aexit__
    
    # Reflection
    trigger_reflection_on_end: bool = True  # Run session reflection at end
    longterm_synthesis_frequency: int = 5  # Auto-synthesize every N sessions
    min_confidence: float = 0.7  # Insight confidence threshold
    min_sessions_for_aggregation: int = 3  # Min sessions before aggregation
    
    # CosmosDB
    database_name: str = "agent_memory_db"
    interactions_container: str = "interactions"
    summaries_container: str = "session_summaries"
    insights_container: str = "insights"
    
    # Azure OpenAI (configured via environment variables)
    # AZURE_OPENAI_REASONING_MODEL - Main agent, CFR, reflection (gpt-4o, gpt-5)
    # AZURE_OPENAI_PROCESSING_MODEL - Metadata generation (gpt-4o-mini)
    # AZURE_OPENAI_EMB_DEPLOYMENT - Embeddings (text-embedding-3-large)
    reasoning_model: Optional[str] = None  # From env: AZURE_OPENAI_REASONING_MODEL
    processing_model: Optional[str] = None  # From env: AZURE_OPENAI_PROCESSING_MODEL
    embedding_model: str = "text-embedding-3-large"
    embedding_dimensions: int = 3072
    
    # Reflection Categories (customizable per domain)
    insight_categories: List[str] = [
        "demographics",
        "financial_goals",
        "risk_profile",
        "current_situation",
        "concern",
        "preference"
    ]
```

### 7.1 Session Pool Configuration (Server Mode)

```python
# Server configuration (environment variables)
MAX_SESSIONS = 1000        # Maximum sessions in LRU cache
SESSION_TTL_MINUTES = 30   # Session cache TTL
EVICTION_INTERVAL_SECONDS = 60  # Background cleanup interval
```

### 7.2 Hidden Tool Injection Configuration

```python
# provider_config.py

@dataclass
class CosmosMemoryProviderConfig:
    inject_recall_tool: bool = True  # Enable hidden tool injection
    recall_tool_name: str = "recall_facts"  # Tool name
    recall_tool_description: str = "Search long-term memory for relevant facts"
```

---

## 8. Financial Advisor Scenario - Prompts

### 8.1 Metadata Generation Prompt (for Interactions)

```python
METADATA_GENERATION_PROMPT = """
You are analyzing a conversation chunk to generate metadata for indexing and retrieval.

Conversation:
{conversation_content}

Generate the following:
1. **summary**: A concise 1-2 sentence summary of this conversation chunk
2. **mentioned_topics**: Array of key topics discussed (max 5)
3. **entities**: Array of specific entities mentioned (products, accounts, amounts, etc.)

Output format: JSON object with keys: summary, mentioned_topics, entities
"""
```

### 8.2 Session Insight Extraction Prompt

```python
SESSION_INSIGHT_EXTRACTION_PROMPT = """
You are analyzing a financial advisory conversation to extract insights about the client.

Session conversation:
{session_conversations}

Your task:
1. Determine if this session contains significant insights worth extracting
2. If yes, extract insights in the following categories:
   - demographics: Age, family status, employment
   - financial_goals: Retirement age, savings targets, major purchases
   - risk_profile: Risk tolerance, investment preferences
   - current_situation: Assets, debts, income, expenses
   - concern: Fears, questions, areas of uncertainty
   - preference: Communication preferences, meeting frequency, etc.

For each insight, provide:
- category: One of the above categories
- insight_text: Clear, concise description
- confidence: Float 0-1 (how confident are you this is accurate)
- importance: "high", "medium", or "low"

Output format: JSON object with:
{{
  "reflection_flag": "insight" or "no-insight",
  "insights": [
    {{
      "category": "...",
      "insight_text": "...",
      "confidence": 0.9,
      "importance": "high"
    }}
  ]
}}

If no significant insights, return {{"reflection_flag": "no-insight", "insights": []}}
"""
```

### 8.3 Long-term Insight Synthesis Prompt

```python
LONGTERM_SYNTHESIS_PROMPT = """
You are creating a comprehensive client profile for a financial advisor.

Current baseline profile:
{baseline_longterm_insight}

New session insights to incorporate:
{new_session_insights}

Your task:
Synthesize a cohesive, comprehensive client profile that:
1. Integrates all new information
2. Resolves any contradictions (favor more recent information)
3. Organizes information logically
4. Maintains a professional, concise tone
5. Focuses on actionable client characteristics

The profile should cover:
- Client demographics and background
- Financial goals and timeline
- Risk tolerance and investment preferences
- Current financial situation
- Key concerns and priorities
- Communication preferences

Output: A well-structured paragraph (200-300 words) summarizing the complete client profile.
"""
```

### 8.4 Cumulative Summary Update Prompt

```python
CUMULATIVE_SUMMARY_PROMPT = """
You are updating a conversation summary for an ongoing session.

Previous summary:
{old_summary}

New conversation turns:
{new_turns}

Generate an updated summary that:
1. Incorporates the new information
2. Maintains key points from the previous summary
3. Removes redundant information
4. Keeps the summary concise (max 100 words)
5. Preserves chronological flow

Output: Updated summary text.
"""
```

---

## 9. File Structure

```
memory/
├── __init__.py
├── orchestrator.py                    # Main coordination layer (MemoryServiceOrchestrator)
├── current_memory_keeper.py           # K-turn buffer management + summarization
├── fact_retrieval.py                  # CFR agent with hybrid search tools
├── reflection.py                      # Session + long-term reflection
├── cosmos_utils.py                    # CosmosDB utilities + embeddings (legacy)
├── cosmos_memory_provider.py          # Remote ContextProvider (HTTP-based)
├── cosmos_memory_provider_embedded.py # Embedded ContextProvider (direct CosmosDB)
├── cosmos_agent_memory.py             # Memory wrapper for direct usage
├── session_pool.py                    # LRU session cache with TTL eviction
├── provider_config.py                 # ContextProvider configuration
├── config.py                          # Memory configuration parameters
├── models.py                          # Pydantic data models
├── prompts.py                         # All prompt templates
└── db/                                # Database abstraction layer
    ├── __init__.py                    # Public exports
    ├── base.py                        # Abstract MemoryDatabase interface
    ├── sqlite_backend.py              # SQLite + sqlite-vec backend
    ├── cosmos_backend.py              # Azure CosmosDB backend
    ├── factory.py                     # Database factory functions
    └── adapters.py                    # Compatibility adapters

server/
├── __init__.py
├── config.py                          # Server configuration
└── main.py                            # FastAPI service

demo/
├── __init__.py
├── setup_cosmosdb.py                  # Create database, containers, indexes
├── hidden_tool_demo.py                # Hidden tool injection demo
├── hidden_tool_demo_remote.py         # Remote service hidden tool demo
├── comparison_tool_injection_demo.py  # Compare hidden vs explicit tools
├── auto_enrichment_demo.py            # Auto-enrichment context demo
├── interactive_demo_live.py           # Interactive demo with live CosmosDB
└── interactive_demo_remote.py         # Interactive demo via remote service

examples/
├── demo1_financial_advisor.py         # Multi-session financial advisor
├── demo1_financial_advisor_embedded.py # Embedded provider version
├── demo2_shopping_assistant.py        # Shopping assistant example
├── demo3_learning_assistant.py        # Learning assistant example
├── demo4_medical_assistant.py         # Medical assistant with allergy check
├── simple_usage.py                    # Minimal usage example
└── simple_usage_sqlite.py             # SQLite database abstraction demo

tests/
├── test_cosmos_agent_memory.py
├── test_cosmos_memory_provider.py
├── test_current_memory_keeper.py
├── test_db_abstraction.py             # Database abstraction layer tests
├── test_fact_retrieval.py
├── test_orchestrator.py
├── test_reflection.py
└── test_session_management.py

infra/
├── main.bicep                         # Azure Bicep deployment
├── main.bicepparam                    # Bicep parameters
└── modules/                           # Modular Bicep resources
```

---

## 9.1 Database Abstraction Layer (`memory/db/`)

The database abstraction layer enables the Agent Memory Service to work with multiple database backends:

| Backend | Status | Server Required | Hybrid Search |
|---------|--------|-----------------|---------------|
| **SQLite + sqlite-vec** | ✅ Implemented | No (embedded) | No (vector-only) |
| **Azure CosmosDB** | ✅ Implemented | Yes (Azure) | Yes (RRF) |
| **PostgreSQL + pgvector** | 🔄 Planned | Yes | No (vector-only) |

### Key Components:

**`base.py`** - Abstract interface:
- `MemoryDatabase`: Abstract base class all backends implement
- `ContainerType`: Enum for interactions, insights, session_summaries
- `SearchResult`: Unified search result format
- `DatabaseCapabilities`: Describes backend features

**`sqlite_backend.py`** - SQLite implementation:
- Uses sqlite-vec extension for native vector search
- Falls back to Python cosine similarity if extension unavailable
- Stores vectors as BLOB, JSON fields as TEXT
- No server required - single file database

**`cosmos_backend.py`** - CosmosDB implementation:
- Native VectorDistance for vector search
- RRF (Reciprocal Rank Fusion) for hybrid search
- FullTextScore for text search
- Enterprise-grade scalability

**`factory.py`** - Database creation:
```python
from memory.db import create_database, DatabaseType

# SQLite (default, no server)
db = create_database(
    db_type=DatabaseType.SQLITE,
    embedding_provider=embedder,
    db_path="memory.db"
)

# CosmosDB (enterprise)
db = create_database(
    db_type=DatabaseType.COSMOSDB,
    embedding_provider=embedder,
    connection_string="..."
)
```

**`adapters.py`** - Compatibility layer:
- `ContainerAdapter`: ContainerProxy-like interface for existing code
- `CosmosUtilsAdapter`: CosmosUtils-like interface for existing code
- `DatabaseBundle`: Provides all adapters needed by orchestrator

### Usage Pattern:

```python
from memory.db import create_database, DatabaseType, ContainerType

# Create and initialize database
db = create_database(DatabaseType.SQLITE, embedding_provider=embedder)
async with db:
    # Store document
    await db.upsert(ContainerType.INTERACTIONS, {
        "id": "int-1",
        "user_id": "user123",
        "content": "...",
        "content_vector": embedder.get_embedding("...")
    })
    
    # Vector search
    results = await db.vector_search(
        ContainerType.INTERACTIONS,
        query_embedding=embedder.get_embedding("query"),
        top_k=5,
        filters={"user_id": "user123"}
    )
```

---

## 10. Implementation Phases

### Phase 1: Foundation (Days 1-2)
- [x] CosmosDB setup (create database, containers, indexes)
- [x] Core data models (`models.py`)
- [x] Memory index implementation (`memory_index.py`)
- [x] Embedding utilities

### Phase 2: Core Components (Days 3-4)
- [x] Current Memory Keeper
- [x] Contextual Fact Retrieval
- [x] Reflection Process
- [x] Memory Service orchestrator

### Phase 3: Agent Integration (Day 5)
- [x] Memory-aware agent wrapper
- [x] Tool integration
- [x] Thread management with memory

### Phase 4: Database Abstraction (Added)
- [x] Abstract MemoryDatabase interface
- [x] SQLite backend with sqlite-vec
- [x] CosmosDB backend (refactored)
- [x] Factory pattern for database creation
- [x] Compatibility adapters for existing code
- [ ] PostgreSQL backend (future)

### Phase 4: Demo & Testing (Days 6-7)
- [ ] Demo data generation
- [ ] Scenario implementations
- [ ] End-to-end testing
- [ ] Documentation

---

## 11. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| **Memory Retrieval Accuracy** | >80% relevant facts retrieved | Manual evaluation on test queries |
| **Context Compression Ratio** | 5:1 (turns:summary) | Token count before/after |
| **Insight Extraction Quality** | >75% useful insights | Human evaluation |
| **Latency** | <500ms for retrieval | Performance testing |
| **Cost Efficiency** | 30% reduction in token usage | Compare with/without compression |

---

## 12. Design Decisions Summary

### ✅ Confirmed Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| **Interaction Granularity** | Multi-turn documents (k turns per document) | Efficient storage, reduces DB operations |
| **Content Format** | Flattened text: `user: ...\nassistant: ...` | Preserves exact conversation flow |
| **Vector Fields** | 2 vectors per interaction (content + summary) | Better retrieval: detailed + high-level |
| **Insight Types** | session + long_term | Clear separation of granularity |
| **Long-term Insights** | Single document per user, **auto-synthesized every N sessions** | Simplified aggregation, automatic lifecycle |
| **Session Init Block** | Static block loaded once at session start | Consistent baseline context |
| **Summarization** | Cumulative update (old + new k turns → new summary) | Maintains full conversation arc |
| **Post-Summarization** | Store in interactions container, remove from active | Efficient memory, preserved in DB |
| **CFR Architecture** | Agent with hybrid search tools (REASONING_MODEL) | Intelligent, flexible retrieval |
| **CFR Container Choice** | Agent decides (interactions, insights, or both) | Context-aware search strategy |
| **Integration Pattern** | ContextProvider (not wrapper) | Non-invasive, Agent Framework native |
| **Hidden Tool Injection** | Auto-inject `recall_facts` tool via `invoking()` | Zero-config memory search |
| **Session Pooling** | LRU cache with TTL eviction | Production performance |
| **Reflection Trigger** | Session: automatic; Long-term: **automatic every N sessions** | Controlled, automatic lifecycle |

### 🔄 Workflow Summary

**Memory Lifecycle:**
```
1. Session Start → Load long-term insight + recent summaries → Init block
2. Conversation → Accumulate k turns → Prune (summarize + store interaction doc)
3. Keep N active turns + cumulative summary
4. Session End → Session reflection → Extract insights (or mark no-insight)
5. Every N sessions → Auto long-term synthesis → Update user profile
```

**Reflection Flow:**
```
Session Reflection (automatic at session end):
  ├─ If insights found → Create session insight docs (processed=false)
  └─ If no insights → Mark session (reflection_status=no-insight)

Long-term Synthesis (automatic every N sessions):
  ├─ Gather unprocessed session insights
  ├─ Synthesize with baseline long-term insight
  ├─ Update long-term insight document (longterm-{user_id})
  └─ Mark session insights as processed=true
```

---

## 13. Next Steps

1. **Review & Approve** this design document
2. **Environment Setup**
   - Create CosmosDB database and containers
   - Verify .env credentials
   - Test embedding generation
3. **Implement Phase 1** (Foundation)
4. **Iterative development** with testing at each phase

---

## 14. References

- **README:** `README.md` - Quick start and usage guide
- **Agent Framework Sample:** `agent/azure_chat_client_with_thread.py`
- **Microsoft Agent Framework Docs:** https://github.com/microsoft/agent-framework
- **Azure CosmosDB Vector Search:** https://learn.microsoft.com/azure/cosmos-db/

---

## 15. Key Implementation Notes

### CosmosDB Schema Highlights
- **interactions**: Multi-turn documents, 2 vectors (content + summary), full-text on 3 fields
- **insights**: Two types (session/long_term), one long-term doc per user
- **session_summaries**: Metadata + reflection tracking

### Memory Keeper Flow
```
Session Init → Load [Long-term insight + Recent summaries]
   ↓
Accumulate turns in buffer (k turns)
   ↓
When buffer full → Generate metadata (gpt-5-nanoo-mini)
   ↓
Create interaction document → Store in CosmosDB
   ↓
Update cumulative summary (old summary + k turns → new summary)
   ↓
Keep only N most recent turns active
   ↓
Repeat until session ends
```

### CFR as Mini-Agent
- Separate agent instance using gpt-5-nanoo-mini
- Has 3 tools: search_interactions, search_insights, search_session_summaries
- Main agent calls CFR via tool: `retrieve_user_facts(query)`
- CFR decides which containers to search and synthesizes results

### Reflection Two-Stage Process
1. **Session Reflection** (automatic at session end):
   - Extract insights or mark "no-insight"
   - Create session insight documents (processed=false)
   
2. **Long-term Reflection** (manual trigger):
   - Aggregate unprocessed session insights
   - Update single long-term insight document
   - Mark session insights as processed=true

### Models Used
- **gpt-5-nano**: Main agent + reflection synthesis
- **gpt-5-nanoo-mini**: CFR agent + metadata generation (summary, topics, entities)
- **text-embedding-ada-002**: All embeddings

---

## 16. Agent Framework Integration

### 16.1 Context Provider Pattern

The memory system integrates with Microsoft Agent Framework using the **Context Provider** pattern. This allows seamless memory injection without modifying the agent's core logic.

**Key Integration Points:**

```python
from agent_framework import ChatAgent
from memory.cosmos_memory_provider import CosmosMemoryProvider

# Create memory provider
memory_provider = CosmosMemoryProvider(
    user_id="user123",
    cosmos_client=cosmos_client,
    openai_client=openai_client,
    config=config
)

# Attach to agent
agent = ChatAgent(
    chat_client=AzureOpenAIChatClient(credential=credential),
    instructions="You are a helpful assistant...",
    tools=[tool1, tool2],
    context_providers=memory_provider  # Memory injected here
)
```

### 16.2 Lifecycle Management

The framework calls specific methods during the agent lifecycle:

| Framework Event | Memory Method Called | Purpose |
|----------------|---------------------|---------|
| `agent.run()` starts | `invoking()` | Inject memory context into thread |
| `agent.run()` completes | `invoked()` | Store turn in memory |
| Context manager enter | `__aenter__()` | Auto-start session if needed |
| Context manager exit | `__aexit__()` | Auto-end session if configured |

**Session Management Modes:**

1. **Automatic Mode** (`auto_manage_sessions=True`):
   - Framework manages sessions via context managers
   - One session per `async with` block
   - Suitable for single-shot conversations

2. **Manual Mode** (`auto_manage_sessions=False`):
   - Application controls session lifecycle
   - Multiple `agent.run()` calls within one session
   - Required for multi-turn conversations
   - Used in all demos

**Manual Session Pattern:**
```python
# Start session manually
await memory_provider._memory.start_session()
memory_provider._session_active = True

try:
    # Multiple agent.run() calls share the same session
    result1 = await agent.run(query1, thread=thread)
    result2 = await agent.run(query2, thread=thread)
    result3 = await agent.run(query3, thread=thread)
finally:
    # End session and trigger reflection
    await memory_provider.end_session_explicit()
```

### 16.3 Memory Context Injection

The `invoking()` method builds and injects memory context:

```
[MEMORY CONTEXT]
=== Long-term Insights ===
<Baseline user profile and preferences>

=== Recent Session Summaries ===
<Summaries from last N sessions>

=== Cumulative Summary ===
<Summary of current session so far>

=== Active Turns ===
<Last M conversation turns>
```

This context is prepended to the thread's message history, providing the agent with rich background without overwhelming the active conversation.

### 16.4 Thread Independence

- Each `agent.get_new_thread()` creates an independent conversation thread
- Memory context is injected per-thread based on user_id and session
- Multiple threads can share the same memory session
- Enables testing memory retention across "new conversations"

### 16.5 Framework Compatibility

**Tested with:**
- Microsoft Agent Framework v1.0.0+
- Python 3.12+
- Azure OpenAI Chat Client
- Async/await patterns

**Key Features:**
- ✅ Non-invasive integration (no agent code changes)
- ✅ Works with any agent instructions and tools
- ✅ Compatible with multiple threads per agent
- ✅ Supports both sync and async patterns
- ✅ Hidden tool injection (`recall_facts`) for on-demand memory search
- ✅ Auto-enrichment with keyword detection (optional)

---

**Document Status:** ✅ Implemented and Tested  
**Last Updated:** January 26, 2026  
**Version:** 3.0 (Consolidated design doc, updated to match implementation)  
**Author:** Agent Memory Service Team
