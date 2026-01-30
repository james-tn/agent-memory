# 🧠 Agent Memory Service

Memory service for AI agents built on **Microsoft Agent Framework**. Enables personalized, context-aware conversations across sessions with support for **SQLite** (local) and **Azure CosmosDB** (enterprise).

## Overview

| Feature | Description |
|---------|-------------|
| **Database Agnostic** | Unified API works with SQLite or CosmosDB |
| **Multi-tier Memory** | Active turns → Cumulative summaries → Session summaries → Long-term insights |
| **Agent Framework Integration** | Native `ContextProvider` with automatic memory injection |
| **Server Mode** | FastAPI service for multi-client support with connection pooling |
| **Hybrid Search** | Vector + full-text search across all memory tiers |
| **Automatic Reflection** | LLM-powered insight extraction at session end |

## Architecture

### Direct Mode (Embedded)

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

### Server Mode (Multi-Client)

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  Python App │  │  TypeScript │  │  Mobile App │
│  (Client)   │  │  (Client)   │  │  (Client)   │
└──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                │                │
       └────────────────┼────────────────┘
                        │ HTTP/REST
          ┌─────────────▼─────────────┐
          │   Memory Service (FastAPI) │
          │   ├─ Session Pool          │  ← Connection pooling
          │   ├─ Background Tasks      │  ← Async reflection
          │   └─ REST API              │  ← Language agnostic
          └─────────────┬─────────────┘
                        │
          ┌─────────────▼─────────────┐
          │  AgentMemory + CosmosDB   │
          └───────────────────────────┘
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

### Server Mode (Multi-Client)

For production with multiple clients (web, mobile, different languages):

```bash
# Start the memory server
uv run python -m uvicorn server.main:app --port 8000
```

```python
from client import MemoryServiceClient

async with MemoryServiceClient("http://localhost:8000", "user123") as client:
    # Start session - retrieves past context
    ctx = await client.start_session()
    
    # Your app handles the conversation...
    user_msg = "What is a Roth IRA?"
    assistant_msg = your_agent.respond(user_msg, context=ctx.context)
    
    # Store turn - background processing handles compression
    await client.store_turn(user_msg, assistant_msg)
    
    # Get updated context for next turn
    ctx = await client.get_context()
    
    # End session - triggers insight extraction
    result = await client.end_session()
    print(f"Summary: {result.summary}")
    print(f"Insights: {result.insights_count}")
```

Server mode benefits:
- **Connection Pooling**: Sessions cached in memory with TTL eviction
- **Background Processing**: Reflection/synthesis don't block client
- **Language Agnostic**: Any HTTP client works (TypeScript, Go, etc.)
- **Centralized**: Single database connection for all clients

### Server Mode + Agent Framework Integration

For the best of both worlds - use `RemoteMemoryProvider` to connect Agent Framework with the memory server:

```python
from agents import Agent
from client import RemoteMemoryProvider

# Create remote memory provider pointing to your server
memory = RemoteMemoryProvider("http://localhost:8000", user_id="user123")

# Create agent with memory as context provider
agent = Agent(
    model=chat_client,
    instructions="You are a financial advisor...",
    context_providers=[memory]  # ← Memory automatically injected!
)

# Run conversation - memory is handled automatically
async with memory:
    # First turn - memory context is injected before agent responds
    response = await agent.run("What did we discuss last time?")
    print(response)
    
    # Second turn - previous turn stored, updated context injected
    response = await agent.run("I got a raise to $120k")
    print(response)
    
    # Third turn - agent has full conversation history
    response = await agent.run("Should I increase my 401k contribution?")
    print(response)

# Session ends automatically - insights extracted on server
```

That's it! The `RemoteMemoryProvider`:
- ✅ Injects personalized context before each agent turn
- ✅ Stores conversation after each response
- ✅ Runs reflection/synthesis on server (no client blocking)
- ✅ Works with any Agent Framework agent
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

### Option 2: Setup Script (Existing CosmosDB Account)

If you already have a CosmosDB account, use the setup script to create containers with proper vector policies:

```bash
# Set environment variables
export COSMOS_ENDPOINT=https://your-account.documents.azure.com:443/
export COSMOS_DATABASE_NAME=agent_memory_db

# Run setup script (creates database + 3 containers with vector indexes)
uv run python scripts/setup_cosmosdb.py
```

The script creates:
- `interactions` container - conversation chunks with `content_vector` and `summary_vector`
- `session_summaries` container - session metadata with `summary_vector`
- `insights` container - long-term insights with `insight_vector`

All containers use `/user_id` as partition key and DiskANN vector indexes for fast similarity search.

### Option 3: Manual Setup

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
   AZURE_COSMOS_DATABASE_NAME=agent_memory_db
   ```

6. **Authenticate** using Azure CLI: `az login`

---

## Examples

| Demo | Mode | Backend | Description |
|------|------|---------|-------------|
| `01_financial_advisor.py` | Direct | SQLite | Agent Framework integration with context providers |
| `02_interactive_streamlit.py` | Server | CosmosDB | Interactive web UI with memory visualization |
| `03_financial_advisor_cosmosdb.py` | Direct | CosmosDB | Direct CosmosDB usage without server |
| `04_financial_advisor_remote.py` | Server | CosmosDB | CLI demo using Memory Service API |
| `05_financial_advisor_direct.py` | Direct | CosmosDB | CLI demo using embedded AgentMemory |

### Quick Start

```bash
# 1. Financial advisor - Direct mode with SQLite (zero-config)
uv run python demo/01_financial_advisor.py

# 2. Interactive Streamlit UI - Server mode with CosmosDB
# First start the server:
uv run python -m uvicorn server.main:app --port 8000
# Then run the demo:
uv run streamlit run demo/02_interactive_streamlit.py

# 3. CLI demos - compare direct vs server mode
uv run python demo/04_financial_advisor_remote.py --scripted  # Server mode
uv run python demo/05_financial_advisor_direct.py --scripted  # Direct mode
```

See [demo/README.md](demo/README.md) for details.

---

## Project Structure

```
agent_memory/
├── memory/                      # Core library
│   ├── __init__.py              # AgentMemory, AgentMemoryConfig exports
│   ├── cosmos_agent_memory.py   # Unified AgentMemory API
│   ├── orchestrator.py          # Memory coordination
│   ├── memory_keeper.py         # K-turn buffer management
│   ├── fact_retrieval.py        # Semantic search
│   ├── reflection.py            # Insight extraction
│   ├── cosmos_utils.py          # CosmosDB + embedding utilities
│   └── config.py                # Configuration
│
├── server/                      # REST API Server
│   ├── main.py                  # FastAPI application
│   └── config.py                # Server configuration
│
├── client/                      # Python Client Library
│   └── memory_client.py         # MemoryServiceClient
│
├── demo/                        # Demo applications
│   ├── 01_financial_advisor.py  # SQLite + Agent Framework
│   ├── 02_interactive_streamlit.py  # Streamlit web UI
│   ├── 03_financial_advisor_cosmosdb.py  # Direct CosmosDB
│   ├── 04_financial_advisor_remote.py    # Server mode CLI
│   └── 05_financial_advisor_direct.py    # Direct mode CLI
│
├── scripts/                     # Utility scripts
│   ├── setup_cosmosdb.py        # Create CosmosDB containers with vector policies
│   └── test_aad_token.py        # Test Azure AD authentication
│
├── infra/                       # Azure infrastructure (Bicep)
│   ├── main.bicep               # Main deployment template
│   └── modules/                 # CosmosDB, OpenAI, Container Apps
│
└── tests/                       # Unit and integration tests
```

---

## API Reference

### AgentMemory (Direct Mode)

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

### MemoryServiceClient (Server Mode)

```python
class MemoryServiceClient:
    def __init__(
        self,
        service_url: str,          # e.g., "http://localhost:8000"
        user_id: str,
        session_id: Optional[str] = None,
        timeout: float = 60.0
    )
    
    # Session lifecycle
    async def start_session() -> SessionContext
    async def end_session(trigger_reflection: bool = True) -> EndSessionResult
    
    # Turn management
    async def store_turn(user_message: str, assistant_message: str) -> TurnResult
    async def get_context() -> SessionContext
    
    # Memory operations
    async def search(query: str, top_k: int = 5) -> str
    async def get_insights(limit: int = 10) -> List[Dict]
    async def get_sessions(limit: int = 10) -> List[Dict]
```

### Memory Service REST API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with active session count |
| `/sessions/start` | POST | Start session, return initial context |
| `/sessions/turn` | POST | Store conversation turn |
| `/sessions/context` | POST | Get current memory context |
| `/sessions/end` | POST | End session, trigger reflection |
| `/search` | POST | Search memory for relevant facts |
| `/users/{user_id}/insights` | GET | Get user's extracted insights |
| `/users/{user_id}/sessions` | GET | Get user's session history |

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

### Local Development

```bash
# Start memory server
uv run python -m uvicorn server.main:app --port 8000 --reload

# Run Streamlit demo
uv run streamlit run demo/02_interactive_streamlit.py
```

### Docker

```bash
docker build -t agent-memory-service .
docker run -p 8000:8000 --env-file .env agent-memory-service
```

### Azure Container Apps

```bash
# Deploy with Azure Developer CLI
azd up
```

## License

MIT


