# Agent Memory Demos

Two demos showcasing the Agent Memory Service:

| Demo | Backend | Focus |
|------|---------|-------|
| **01_financial_advisor.py** | SQLite | Agent Framework integration, context providers |
| **02_interactive_streamlit.py** | CosmosDB | Interactive web UI, memory visualization |

---

## Demo 1: Financial Advisor (Agent Framework + SQLite)

A multi-session financial advisor demonstrating:
- **AgentMemory as a context provider** for ChatAgent
- **Automatic context retrieval** at each session start
- **Multi-session memory persistence** with SQLite (zero-config)
- **Insight extraction** at session end

### Run

```bash
uv run python -m demos.01_financial_advisor
```

### Scenario

| Session | User Actions | Memory Behavior |
|---------|--------------|-----------------|
| 1 | Shares profile: age 35, $150k income, moderate-high risk | Memory stores facts |
| 2 | Asks about asset allocation | Agent recalls risk profile automatically |
| 3 | Asks about tax optimization | Agent uses all accumulated context |

### Key Code Pattern

```python
from memory import AgentMemory, AgentMemoryConfig
from agent_framework import ChatAgent

# Create memory with auto-enrichment
config = AgentMemoryConfig(auto_enrich_context=True)
memory = AgentMemory(user_id="sarah", openai_client=client, config=config)

# Pass memory as context_provider - that's it!
agent = ChatAgent(
    chat_client=chat_client,
    instructions="You are a financial advisor...",
    context_providers=[memory],  # ← Automatic integration
)

# Memory is automatically managed:
# - invoking(): injects context before each turn
# - invoked(): stores turns after each response
await memory.start_session()
response = await agent.run("What's my risk tolerance?")  # No manual add_turn!
await memory.end_session()  # Extracts insights
```

---

## Demo 2: Interactive Streamlit (CosmosDB)

A rich web UI for exploring all memory features:
- **Real-time chat** with memory-aware financial advisor
- **Memory visualization** (context, insights, sessions)
- **Semantic search** across all memory tiers
- **CosmosDB backend** for production-grade vector search

### Prerequisites

1. Azure CosmosDB with vector search enabled
2. Set environment variables:
   ```bash
   COSMOS_ENDPOINT=https://your-account.documents.azure.com:443/
   ```

### Run

```bash
# Install streamlit if needed
pip install streamlit

# Run the demo
streamlit run demos/02_interactive_streamlit.py
```

### Features

| Feature | Description |
|---------|-------------|
| 💬 Chat | Converse with the memory-aware advisor |
| 📚 Context View | See current memory context (turns + summaries + insights) |
| 💡 Insights | Browse extracted user insights |
| 📅 Sessions | View session history and summaries |
| 🔍 Search | Semantic search across all memory |

---

## Environment Setup

### Minimal (Demo 1 only)

```bash
# .env file
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_REASONING_MODEL=gpt-4o
AZURE_OPENAI_PROCESSING_MODEL=gpt-4o-mini
AZURE_OPENAI_EMB_DEPLOYMENT=text-embedding-ada-002
```

### Full (Both demos)

```bash
# .env file (add CosmosDB for Demo 2)
COSMOS_ENDPOINT=https://your-cosmos.documents.azure.com:443/
AZURE_COSMOS_DATABASE_NAME=agent_memory_db
```

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│  Your Agent (ChatAgent + context_providers)    │
│                      │                          │
│         ┌────────────▼────────────┐             │
│         │  AgentMemory            │             │
│         │  ├─ get_context()       │ ← Per-turn  │
│         │  ├─ add_turn()          │             │
│         │  └─ search()            │ ← On-demand │
│         └────────────┬────────────┘             │
└──────────────────────┼──────────────────────────┘
                       │
        ┌──────────────▼──────────────┐
        │  Database Backend           │
        │  ├─ SQLite (Demo 1)         │
        │  └─ CosmosDB (Demo 2)       │
        └─────────────────────────────┘
```
