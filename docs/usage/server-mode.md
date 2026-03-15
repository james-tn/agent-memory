# Server Mode

Server mode is useful when memory is shared across multiple clients or services.

## Start the Service

```bash
uv run uvicorn server.main:app --host 127.0.0.1 --port 8000
```

The server initializes its shared backend on startup so configuration problems fail fast.

## Python Client Example

```python
from client.memory_client import MemoryServiceClient

async with MemoryServiceClient("http://127.0.0.1:8000", "user-123") as client:
    ctx = await client.start_session()
    await client.store_turn("Remember I prefer train travel.", "Understood.")
    results = await client.search("travel preference", search_mode="hybrid")
    await client.end_session()
```

## What the Client Supports

- `health_check()`
- `start_session()`
- `get_context()`
- `store_turn()`
- `end_session()`
- `search()`
- `get_insights()`
- `get_sessions()`

## Backend Switching

Server mode respects `AGENT_MEMORY_DB_TYPE`, so the same service can be backed by SQLite, Cosmos DB, Azure AI Search, or PostgreSQL.
