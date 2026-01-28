# Agent Memory Service - Demos

Comprehensive demonstrations of the Agent Memory Service with the unified API.

## Quick Start

```bash
# From project root
cd c:\testing\agent_memory

# Run quickstart demo
uv run python -m demos.quickstart.usage

# Or run the scenario demo
uv run python -m demos.scenarios.financial_advisor
```

## Unified API

The new unified `AgentMemory` API provides a single interface that works with any backend:

```python
from memory import AgentMemory
from memory.db.factory import DatabaseType

# SQLite (default - no server required!)
async with AgentMemory(user_id="user123", openai_client=client) as memory:
    await memory.add_turn("Hello", "Hi there!")
    context = memory.get_context()
    facts = await memory.search("user preferences")

# CosmosDB (same API, different backend)
memory = AgentMemory(
    user_id="user123",
    openai_client=client,
    db_type=DatabaseType.COSMOSDB,
    cosmos_endpoint=os.getenv("COSMOS_ENDPOINT")  # Uses AAD auth
)
```

## Folder Structure

```
demos/
├── quickstart/           # Getting-started examples
│   └── usage.py          # All 5 examples with both SQLite and CosmosDB
└── scenarios/            # Real-world use case demos
    └── financial_advisor.py  # Multi-session financial advisor
```

## Backend Options

| Backend | Requirements | Best For |
|---------|--------------|----------|
| **SQLite** | Azure OpenAI only | Local development, testing, edge deployments |
| **CosmosDB** | Azure CosmosDB + Azure OpenAI | Production, cloud deployments |

---

## Demo Details

### quickstart/usage.py

Demonstrates all features of the API:

1. **Example 1: SQLite with Async Context Manager** - Basic usage
2. **Example 2: SQLite Multi-Session** - Memory persistence across sessions
3. **Example 3: SQLite Memory Search** - Vector similarity search
4. **Example 4: CosmosDB with AAD Auth** - Enterprise production setup
5. **Example 5: SQLite with Factory Function** - Using `create_agent_memory()`

### scenarios/financial_advisor.py

Full financial advisor with multi-session memory:
- Session 1: Client discusses retirement planning, reveals risk profile
- Session 2: Investment questions - agent recalls risk tolerance
- Session 3: Tax strategies - agent uses all accumulated context

---

## Environment Setup

### For SQLite Demos (Minimal)
Only Azure OpenAI is required:

```bash
# .env file
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_REASONING_MODEL=gpt-5.1-chat
AZURE_OPENAI_PROCESSING_MODEL=gpt-5.1-chat
AZURE_OPENAI_EMB_DEPLOYMENT=text-embedding-ada-002
```

### For CosmosDB Demos (Full)
Requires Azure CosmosDB with AAD authentication:

```bash
# .env file (additional)
COSMOS_ENDPOINT=https://your-cosmos.documents.azure.com:443/
AZURE_COSMOS_DATABASE_NAME=agent_memory
AZURE_COSMOS_INTERACTIONS_CONTAINER=interactions
AZURE_COSMOS_INSIGHTS_CONTAINER=insights
AZURE_COSMOS_SUMMARIES_CONTAINER=session_summaries
```

---

## Benefits of SQLite Backend

- **No database server** - Single file storage
- **No extra Azure credentials** - Works with just Azure OpenAI
- **Fast testing** - Instant setup for development
- **Portable** - Copy the .db file anywhere
- **Same API** - Easy migration to CosmosDB for production
