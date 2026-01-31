# Agent Memory Demos

Demos organized from **simple → complex** and **local → production**:

| # | Demo | Backend | Complexity | Focus |
|---|------|---------|------------|-------|
| 01 | [Basic Memory](01_basic_memory.py) | SQLite | ⭐ | Manual `add_turn()` + `get_context()` - no framework |
| 02 | [Agent Framework](02_agent_framework.py) | SQLite | ⭐⭐ | Auto context injection via `context_providers` |
| 03 | [Agent-Driven](03_agent_driven.py) | SQLite | ⭐⭐⭐ | Explicit memory tools - agent controls searches |
| 04 | [CosmosDB](04_cosmosdb.py) | CosmosDB | ⭐⭐ | Same as 02 but with production backend |
| 05 | [Server Mode](05_server_mode.py) | CosmosDB | ⭐⭐⭐ | Client/server architecture for multi-client apps |
| 06 | [Insight Curation](06_insight_curation.py) | SQLite | ⭐⭐⭐ | Contradiction resolution & profile evolution |
| 07 | [Interactive UI](07_interactive_ui.py) | CosmosDB | ⭐⭐⭐⭐ | Full Streamlit web UI with visualization |
| 08 | [Itemized Insights](08_itemized_insights.py) | SQLite | ⭐⭐⭐ | Memory prioritization: recency, frequency, bounded memory |
| 09 | [Itemized Insights CosmosDB](09_itemized_insights_cosmos.py) | CosmosDB | ⭐⭐⭐ | Same as 08 but with production CosmosDB backend |

---

## Quick Start

```bash
# Simplest - just run it (SQLite, no dependencies)
uv run python demo/01_basic_memory.py

# Agent Framework integration
uv run python demo/02_agent_framework.py

# Agent-controlled memory tools
uv run python demo/03_agent_driven.py
```

---

## Demo 01: Basic Memory (Simplest)

**The simplest way to use AgentMemory** - no Agent Framework required.

Also demonstrates **automatic buffer management** for long conversations:
- Configure `buffer_size` (when to summarize) and `active_turns` (how many to keep)
- Older turns are automatically compressed into a running summary
- Context size stays bounded regardless of conversation length

```python
from memory import AgentMemory, AgentMemoryConfig

# Configure buffer management for long conversations
config = AgentMemoryConfig(
    buffer_size=6,      # Summarize when buffer reaches 6 turns
    active_turns=4,     # Keep last 4 turns after pruning
)

async with AgentMemory(user_id="user123", openai_client=client, config=config) as memory:
    # Store conversation turns manually
    await memory.add_turn("Hi!", "Hello! How can I help?")
    await memory.add_turn("What's AI?", "AI is artificial intelligence...")
    # ... many more turns - older ones get summarized automatically
    
    # Get formatted context for your LLM prompt
    context = memory.get_context()  # Always bounded size!
    
    # Search for specific information
    results = await memory.search("user preferences")
    
    # End session - extracts insights
    await memory.end_session()
```

**When to use:** Quick prototyping, integrating with any LLM framework, understanding how memory works.

---

## Demo 02: Agent Framework Integration

**Automatic memory management** with Microsoft Agent Framework.

```python
from agent_framework import ChatAgent
from memory import AgentMemory, AgentMemoryConfig

config = AgentMemoryConfig(auto_enrich_context=True, enrichment_mode="llm")
memory = AgentMemory(user_id="user123", openai_client=client, config=config)

# Just pass memory as context_provider - everything is automatic!
agent = ChatAgent(
    chat_client=chat_client,
    instructions="You are a financial advisor...",
    context_providers=[memory]
)

async with memory:
    await memory.start_session()
    response = await agent.run("What's my risk tolerance?")
    # Memory automatically injected + stored!
    await memory.end_session()
```

**When to use:** Most applications. Let the system handle memory automatically.

---

## Demo 03: Agent-Driven Memory

**Agent explicitly controls when to search memory** via tools.

```python
@tool(name="search_memory", description="Search patient history")
async def search_memory(query: str) -> str:
    return await memory.search(query, search_interactions=True, search_insights=True)

agent = ChatAgent(
    chat_client=chat_client,
    instructions="ALWAYS search memory before prescribing medications.",
    tools=[search_memory],
    context_providers=[memory]  # Still stores turns automatically
)
```

**When to use:** Safety-critical applications (medical, legal) where memory access should be visible and auditable.

---

## Demo 04: CosmosDB Backend

Same as Demo 02 but with **Azure CosmosDB** for production:
- Global distribution
- Vector search at scale  
- Enterprise security (AAD auth)

```python
from memory.db import DatabaseType

memory = AgentMemory(
    user_id="user123",
    openai_client=client,
    db_type=DatabaseType.COSMOSDB,
    cosmos_endpoint=os.getenv("COSMOS_ENDPOINT")
)
```

**Prerequisites:** Azure CosmosDB account with vector search. See [infra/README.md](../infra/README.md).

---

## Demo 05: Server Mode

**Client/server architecture** for multi-client applications:

```bash
# Terminal 1: Start memory server
uv run uvicorn server.main:app --port 8000

# Terminal 2: Run demo
uv run python demo/05_server_mode.py
```

```python
from client import MemoryServiceClient

async with MemoryServiceClient("http://localhost:8000", "user123") as client:
    ctx = await client.start_session()
    await client.store_turn(user_msg, assistant_msg)
    await client.end_session()
```

**When to use:** Multiple clients (web, mobile, different languages), microservices, centralized memory.

---

## Demo 06: Insight Curation

**Demonstrates how long-term insights evolve over time:**
- Profile evolution as user preferences change
- Contradiction resolution (old preferences replaced by new)
- Outdated information pruning
- **Real LLM verification** that the profile actually affects agent behavior

**Key Configuration:**
```python
config = AgentMemoryConfig(
    buffer_size=6,
    longterm_synthesis_frequency=1,  # Synthesize after EVERY session
)
```

**Scenario:** A financial advisor client whose risk tolerance evolves:
1. **Session 1:** New graduate, conservative, avoids stocks completely (simulated)
2. **Session 2:** Promoted to $120k, now aggressive 90% stocks (simulated)  
3. **Session 3:** Real LLM conversation - user's dad says "play it safe" but agent should know user is now aggressive

**What to observe:** 
- The long-term profile updates to reflect the user's CURRENT stance (aggressive)
- The final session uses a real LLM response that proves the agent knows the evolved profile
- The agent respectfully disagrees with conservative advice because it knows the user's preferences have changed

```bash
uv run python demo/06_insight_curation.py
```

---

## Demo 07: Interactive UI

**Full-featured Streamlit web application:**
- Real-time chat with memory-aware agent
- Memory visualization (turns, summaries, insights)
- Semantic search explorer
- Pre-built demo scenarios

```bash
# Start server first
uv run uvicorn server.main:app --port 8000

# Run Streamlit app
streamlit run demo/07_interactive_ui.py
```

---

## Demo 08: Itemized Insights (Memory Prioritization)

**Demonstrates human-like memory with bounded capacity:**
- Each insight is individually tracked with ID, timestamp, access count
- LLM cites existing insights during reflection (strengthening them)
- Retention score based on **Ebbinghaus forgetting curve**
- Maximum 5 insights retained - least relevant are pruned

**Key Concepts:**
1. **RECENCY**: New insights get a 7-day "grace period" boost (like fresh memories being more vivid)
2. **FREQUENCY**: Cited insights increase `access_count`, slowing decay (rehearsal strengthens memory)
3. **FORGETTING**: Old, uncited insights decay exponentially over time
4. **BOUNDED MEMORY**: Only top-5 scored insights are retained (like human working memory limits)

**6-Month Simulation:** Runs 6 financial advisor sessions with simulated dates, showing how:
- INS-0001 (conservative preference) survives for months due to frequent citation
- INS-0002, INS-0003 are forgotten early (never cited again)
- New insights compete for limited memory slots
- Eventually even INS-0001 is forgotten when outcompeted by newer insights

```bash
uv run python demo/08_itemized_insights.py
```

**Scoring Formula (Ebbinghaus-inspired):**
```python
def calculate_retention_score(item, now):
    # Decay over time (30-day half-life, adjusted by access_count)
    days_since_access = (now - item.last_accessed).days
    strength = 1.0 + math.log1p(item.access_count)  # More access = slower decay
    retention = math.exp(-days_since_access / (30 * strength))
    
    # New insights get a temporary boost
    recency_boost = 0.3 if (now - item.date_added).days < 7 else 0.0
    
    return (retention + recency_boost) * importance_weight * confidence_factor
```

---

## Demo 09: Itemized Insights (CosmosDB)

**Same as Demo 08 but with Azure CosmosDB backend:**
- Production-ready with global distribution
- Vector search at scale
- Enterprise security (Azure AD authentication)
- Schema-less storage - new fields work automatically

```bash
# Requires COSMOS_ENDPOINT (and optionally COSMOS_KEY, or Azure AD auth)
uv run python demo/09_itemized_insights_cosmos.py
```

**Authentication Options:**
1. **Key-based**: Set `COSMOS_KEY` environment variable
2. **Azure AD**: Uses `DefaultAzureCredential` if no key is set

---

## Environment Setup

```bash
# Required
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_REASONING_MODEL=gpt-4o
AZURE_OPENAI_EMB_DEPLOYMENT=text-embedding-ada-002

# For CosmosDB demos (04, 05, 06)
COSMOS_ENDPOINT=https://your-account.documents.azure.com:443/
```

---

## Comparison: Memory Patterns

| Pattern | Demos | Context Injection | Turn Storage | Memory Search |
|---------|-------|-------------------|--------------|---------------|
| **Manual** | 01 | You call `get_context()` | You call `add_turn()` | You call `search()` |
| **Auto-Context** | 02, 04 | Automatic via `invoking()` | Automatic via `invoked()` | LLM-triggered |
| **Agent-Driven** | 03 | Minimal (session summary) | Automatic via `invoked()` | Agent calls `search_memory` tool |
