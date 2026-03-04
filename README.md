# 🧠 Agent Memory Service

Memory service for AI agents built on **Microsoft Agent Framework**. Enables personalized, context-aware conversations across sessions with support for **SQLite** (local) and **Azure CosmosDB** (enterprise).

## Overview

| Feature | Description |
|---------|-------------|
| **Database Agnostic** | Unified API works with SQLite or CosmosDB |
| **Multi-tier Memory** | Active turns → Cumulative summaries → Session summaries → Long-term insights |
| **Agent Framework Integration** | Native `ContextProvider` with automatic memory injection |
| **Hybrid Search** | Vector + full-text search across all memory tiers |
| **Automatic Reflection** | LLM-powered insight extraction at session end |

## Architecture

```
Your AI Agent (Agent Framework + AgentMemory)
                    │
    ┌───────────────▼───────────────┐
    │  AgentMemory (Unified API)    │
    │  ├─ MemoryOrchestrator        │
    │  │   ├─ MemoryKeeper          │  ← k-turn buffer
    │  │   ├─ FactRetrieval         │  ← hybrid search
    │  │   └─ Reflection            │  ← insight extraction
    └───────────────┬───────────────┘
                    │
    ┌───────────────▼───────────────┐
    │  Database Backend (Pluggable) │
    │  ├─ SQLiteDatabase            │  ← Local file storage
    │  └─ CosmosDBDatabase          │  ← Azure enterprise
    └───────────────────────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- Azure OpenAI service with:
  - `gpt-5.1-chat` deployment for reasoning
  - `text-embedding-ada-002` for embeddings
- Optional: Azure CosmosDB for production

### Installation

```bash
cd agent_memory
uv sync  # or: pip install -e .
```

### Configuration

Create a `.env` file:

```bash
# Azure OpenAI (required)
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_REASONING_MODEL=gpt-5.1-chat
AZURE_OPENAI_PROCESSING_MODEL=gpt-5.1-chat
AZURE_OPENAI_EMB_DEPLOYMENT=text-embedding-ada-002

# Azure CosmosDB (optional - for production)
COSMOS_ENDPOINT=https://your-account.documents.azure.com:443/
AZURE_COSMOS_DATABASE_NAME=agent_memory
```

---

## Usage

### Simple Usage (SQLite - Default)

```python
from openai import AzureOpenAI
from memory import AgentMemory

client = AzureOpenAI(...)

# SQLite backend - no server required!
async with AgentMemory(user_id="user123", openai_client=client) as memory:
    await memory.add_turn("Hello!", "Hi there!")
    context = memory.get_context()
    print(context)  # Formatted memory for AI prompt
```

### Production Usage (CosmosDB)

```python
from memory import AgentMemory
from memory.db.factory import DatabaseType

# CosmosDB with AAD authentication
memory = AgentMemory(
    user_id="user123",
    openai_client=client,
    db_type=DatabaseType.COSMOSDB,
    cosmos_endpoint=os.getenv("COSMOS_ENDPOINT")  # Uses DefaultAzureCredential
)

async with memory:
    await memory.add_turn("What stocks should I buy?", "Based on your conservative profile...")
    facts = await memory.search("risk tolerance")
```

### Agent Framework Integration

```python
from agent_framework import ChatAgent
from memory import AgentMemory, AgentMemoryConfig

# Enable auto-enrichment for keyword-triggered memory search
config = AgentMemoryConfig(auto_enrich_context=True)
memory = AgentMemory(user_id="user123", openai_client=client, config=config)

# Pass memory as context_provider - everything is automatic!
agent = ChatAgent(
    chat_client=chat_client,
    instructions="You are a helpful assistant...",
    context_providers=[memory]  # ← Automatic memory injection
)

# Memory automatically:
# 1. Injects context before each turn (via invoking())
# 2. Stores conversation after each turn (via invoked())
async with memory:
    result = await agent.run("What did we discuss last time?")
    # No manual add_turn() needed!
```
---

## Memory Tiers

| Tier | Description | Lifecycle |
|------|-------------|-----------|
| **Active Turns** | Last K turns in buffer | Pruned when buffer fills |
| **Cumulative Summary** | Rolling summary of current session | Updated at each prune |
| **Session Summaries** | Per-session summaries with topics | Loaded at session start |
| **Long-term Insights** | User profile synthesized from sessions | Auto-synthesized every N sessions |

---

## CosmosDB Setup

For production deployments, use Azure CosmosDB with vector search. Two options:

### Option 1: Azure Developer CLI (Recommended)

Deploy everything with a single command:

```bash
# Install azd if needed
winget install Microsoft.Azd

# Deploy infrastructure (CosmosDB + OpenAI + Container Apps)
cd agent_memory
azd up
```

This creates:
- CosmosDB account with vector search enabled
- Database `agent_memory_db` with 3 containers (interactions, session_summaries, insights)
- Vector indexes (1536 dimensions, cosine distance)
- RBAC roles for AAD authentication
- Azure OpenAI with required model deployments

See [infra/README.md](infra/README.md) for details.

### Option 2: Manual Setup

1. **Create CosmosDB Account** with NoSQL API and vector search capability
2. **Create Database**: `agent_memory_db`
3. **Create Containers** with partition key `/user_id`:
   - `interactions` - conversation chunks with vector embeddings
   - `session_summaries` - session metadata with vector search
   - `insights` - long-term user insights

4. **Configure Vector Policies** (example for interactions container):
   ```json
   {
     "vectorEmbeddings": [{
       "path": "/content_vector",
       "dataType": "float32",
       "dimensions": 1536,
       "distanceFunction": "cosine"
     }]
   }
   ```

5. **Set Environment Variables**:
   ```bash
   COSMOS_ENDPOINT=https://your-account.documents.azure.com:443/
   AZURE_COSMOS_DATABASE_NAME=agent_memory
   ```

6. **Authenticate** using Azure CLI: `az login`

---

## Examples

| Demo | Backend | Description |
|------|---------|-------------|
| `01_financial_advisor.py` | SQLite | Agent Framework integration with context providers |
| `02_interactive_streamlit.py` | CosmosDB | Interactive web UI with memory visualization |

### Quick Start Demo

```bash
# Financial advisor - Agent Framework + SQLite (zero-config)
uv run python -m demos.01_financial_advisor

# Interactive Streamlit UI - requires CosmosDB
streamlit run demos/02_interactive_streamlit.py
```

See [demos/README.md](demos/README.md) for details.

---

## Project Structure

```
memory/
├── core/                    # Core components
│   ├── agent_memory.py      # Unified AgentMemory API
│   ├── orchestrator.py      # Memory coordination
│   ├── memory_keeper.py     # K-turn buffer management
│   ├── fact_retrieval.py    # Semantic search
│   └── reflection.py        # Insight extraction
├── db/                      # Database backends
│   ├── base.py              # Abstract base class
│   ├── factory.py           # Backend factory
│   ├── sqlite_backend.py    # SQLite implementation
│   └── cosmos_backend.py    # CosmosDB implementation
├── providers/               # Embedding providers
│   └── embedding.py         # OpenAI embeddings
├── models.py                # Data models
└── prompts.py               # LLM prompts

demos/
├── quickstart/              # Getting started
│   └── usage.py             # Complete API demo
└── scenarios/               # Use cases
    └── financial_advisor.py
```

---

## API Reference

### AgentMemory

```python
class AgentMemory:
    def __init__(
        self,
        user_id: str,
        openai_client: AzureOpenAI,
        db_type: DatabaseType = DatabaseType.SQLITE,
        db_path: str = "agent_memory.db",           # SQLite
        cosmos_endpoint: str = None,                 # CosmosDB
        cosmos_connection_string: str = None,        # CosmosDB (alternative)
        embedding_model: str = "text-embedding-ada-002",
        k_turns: int = 5,
        m_sessions: int = 5,
    )
    
    # Core methods
    async def add_turn(user_message: str, assistant_message: str)
    def get_context() -> str
    async def search(query: str, top_k: int = 5) -> List[SearchResult]
    async def end_session()  # Triggers reflection
```

### Database Factory

```python
from memory.db.factory import create_database, DatabaseType

# SQLite
db = create_database(DatabaseType.SQLITE, db_path="memory.db")

# CosmosDB
db = create_database(
    DatabaseType.COSMOSDB,
    endpoint=os.getenv("COSMOS_ENDPOINT"),
    embedding_dimensions=1536
)
```

---

## Testing

```bash
# Run all tests
uv run pytest tests/

# Run specific test
uv run pytest tests/test_lifecycle.py -v
```

---

## Deployment

### Docker

```bash
docker build -t agent-memory-service .
docker run -p 8000:8000 --env-file .env agent-memory-service
```

### Azure Container Apps

See [infra/README.md](infra/README.md) for Bicep templates.

---

## License

MIT


