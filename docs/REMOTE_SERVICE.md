# Remote Memory Service Guide

This guide covers the FastAPI-based remote memory service that provides high-performance, language-agnostic memory for conversational agents.

## Architecture

```
┌─────────────────────┐
│  Client Application │  (Any language)
│  - Agent/Chat logic │
│  - Business code    │
└──────────┬──────────┘
           │ HTTP/REST
           ▼
┌─────────────────────┐
│  Memory API Service │  (FastAPI)
│  - Session pooling  │
│  - Resource sharing │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│    CosmosDB + AI    │
│  - Interactions     │
│  - Summaries        │
│  - Insights         │
└─────────────────────┘
```

## Key Benefits

### 🚀 Performance
- **0ms session restoration** for hot sessions (in-memory pool)
- **100x faster** than querying CosmosDB each turn
- **Shared resource pooling** (single OpenAI/CosmosDB clients for all users)

### 🔧 Simplicity
- **No database setup** in client code
- **Just HTTP calls** - works from any language
- **Automatic session management** with CosmosMemoryProvider

### 📈 Scalability
- **LRU eviction** handles thousands of concurrent users
- **Automatic cleanup** of stale sessions
- **Graceful degradation** if memory service unavailable

## Quick Start

### 1. Install Dependencies

```bash
# From agent_memory directory
pip install -e .
```

### 2. Configure Environment

```bash
# Copy example config
cp .env.example .env

# Edit .env with your Azure credentials
# Required:
# - AZURE_OPENAI_ENDPOINT
# - AZURE_OPENAI_API_KEY
# - AZURE_OPENAI_DEPLOYMENT
# - COSMOS_ENDPOINT
# - COSMOS_KEY
```

### 3. Start Memory Service

```bash
python run_server.py
```

Expected output:
```
============================================================
🚀 Starting Agent Memory Service
============================================================
Host: 0.0.0.0:8000
Session Pool: max=1000, ttl=30min
CosmosDB: agent_memory
OpenAI: gpt-4
============================================================
INFO:     Started server process [12345]
INFO:     Waiting for application startup.
✓ Azure OpenAI client initialized: gpt-4
✓ Cosmos DB containers initialized: agent_memory
✓ CosmosUtils initialized with embeddings: text-embedding-ada-002
✓ Session pool initialized: max=1000, ttl=30min
✅ Memory Service ready!
INFO:     Application startup complete.
```

### 4. Test with Demo

```bash
# In another terminal
python examples/demo1_remote.py
```

## Usage Patterns

### Pattern 1: Agent Framework (Recommended)

Uses `CosmosMemoryProvider` which automatically integrates with agent lifecycle.

```python
from memory.cosmos_memory_provider import CosmosMemoryProvider
from agent_framework import ChatAgent

async with CosmosMemoryProvider(
    service_url="http://localhost:8000",
    user_id="user123",
    auto_manage_session=True
) as memory_provider:
    
    agent = ChatAgent(
        chat_client=...,
        instructions="You are a helpful assistant...",
        context_providers=[memory_provider]
    )
    
    # Memory automatically injected before each turn
    # and stored after each response
    response = await agent.run("What did we discuss last time?")
    
    # End session (triggers reflection)
    await memory_provider.end_session()
```

### Pattern 2: Generic Python Client

Uses `MemoryServiceClient` for manual control without Agent Framework.

```python
from client.memory_client import MemoryServiceClient

async with MemoryServiceClient(
    service_url="http://localhost:8000",
    user_id="user123"
) as client:
    
    # Start session
    context = await client.start_session()
    print(context["formatted_context"])  # Inject into your agent's prompt
    
    # Store turns manually
    await client.store_turn(
        user_message="What is a 401k?",
        agent_message="A 401k is a retirement savings plan..."
    )
    
    # Get updated context
    context = await client.get_context()
    
    # End session
    await client.end_session()
```

### Pattern 3: Any Language (cURL/HTTP)

Direct HTTP calls work from any language.

```bash
# Start session
curl -X POST http://localhost:8000/sessions/start \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user123"}'

# Response includes session_id and initial context
# {
#   "session_id": "abc123",
#   "formatted_context": "...",
#   "insights": [...],
#   ...
# }

# Store turn
curl -X POST http://localhost:8000/memory/store \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "session_id": "abc123",
    "user_message": "What is a 401k?",
    "agent_message": "A 401k is a retirement savings plan..."
  }'

# End session
curl -X POST http://localhost:8000/sessions/end \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user123", "session_id": "abc123"}'
```

## API Reference

### Session Management

#### `POST /sessions/start`

Start a new session or restore existing one.

**Request:**
```json
{
  "user_id": "user123",
  "session_id": "optional-session-id",  // Auto-generated if not provided
  "restore": true  // Attempt to restore if session exists
}
```

**Response:**
```json
{
  "session_id": "abc123",
  "user_id": "user123",
  "active_context": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "cumulative_summary": "Summary of earlier conversation...",
  "insights": ["User prefers conservative investments", ...],
  "session_summaries": ["Previous session discussed 401k", ...],
  "formatted_context": "Ready-to-inject context string",
  "restored": true  // Whether session was restored from CosmosDB
}
```

#### `POST /sessions/end`

End session and trigger reflection.

**Request:**
```json
{
  "user_id": "user123",
  "session_id": "abc123"
}
```

### Memory Operations

#### `POST /memory/context`

Get current session context.

**Request:**
```json
{
  "user_id": "user123",
  "session_id": "abc123"
}
```

**Response:** Same as `/sessions/start`

#### `POST /memory/store`

Store a conversation turn.

**Request:**
```json
{
  "user_id": "user123",
  "session_id": "abc123",
  "user_message": "What is a 401k?",
  "agent_message": "A 401k is a retirement savings plan..."
}
```

#### `POST /memory/retrieve`

Retrieve contextual facts via semantic search.

**Request:**
```json
{
  "user_id": "user123",
  "session_id": "abc123",
  "query": "What did we discuss about retirement?",
  "top_k": 5
}
```

**Response:**
```json
{
  "query": "What did we discuss about retirement?",
  "facts": [
    "User wants to retire at 65",
    "User has conservative risk tolerance",
    ...
  ],
  "count": 5
}
```

### Insights & Summaries

#### `POST /insights`

Get user insights (long-term learnings).

**Request:**
```json
{
  "user_id": "user123",
  "recent_only": false
}
```

#### `POST /summaries`

Get session summaries.

**Request:**
```json
{
  "user_id": "user123",
  "limit": 5
}
```

### Health & Monitoring

#### `GET /health`

Health check endpoint.

#### `GET /stats`

Get session pool statistics.

**Response:**
```json
{
  "total_sessions": 42,
  "dirty_sessions": 5,
  "max_capacity": 1000,
  "utilization": 0.042,
  "ttl_seconds": 1800,
  "avg_age_seconds": 245.3,
  "oldest_age_seconds": 890.1
}
```

## Configuration

All settings can be configured via environment variables (see `.env.example`):

### Server Settings
- `HOST`: Server host (default: `0.0.0.0`)
- `PORT`: Server port (default: `8000`)
- `RELOAD`: Auto-reload on code changes (default: `false`)
- `LOG_LEVEL`: Logging level (default: `INFO`)

### Session Pool
- `MAX_SESSIONS`: Maximum sessions in memory (default: `1000`)
- `SESSION_TTL_MINUTES`: Minutes before eviction eligibility (default: `30`)
- `EVICTION_INTERVAL_SECONDS`: Background cleanup interval (default: `60`)

### Azure OpenAI
- `AZURE_OPENAI_ENDPOINT`: OpenAI endpoint URL
- `AZURE_OPENAI_API_KEY`: API key
- `AZURE_OPENAI_DEPLOYMENT`: Deployment name (e.g., `gpt-4`)
- `AZURE_OPENAI_API_VERSION`: API version (default: `2024-02-15-preview`)

### Azure Cosmos DB
- `COSMOS_ENDPOINT`: CosmosDB endpoint URL
- `COSMOS_KEY`: CosmosDB key
- `COSMOS_DATABASE_NAME`: Database name (default: `agent_memory`)
- `COSMOS_INTERACTIONS_CONTAINER`: Interactions container (default: `interactions`)
- `COSMOS_SUMMARIES_CONTAINER`: Summaries container (default: `session_summaries`)
- `COSMOS_INSIGHTS_CONTAINER`: Insights container (default: `insights`)

### Memory Settings
- `K_TURN_BUFFER`: Recent turns in active memory (default: `5`)
- `L_TURN_CHUNKS`: Turns per interaction chunk (default: `10`)
- `M_SESSIONS_RECENT`: Recent sessions in context (default: `5`)
- `REFLECTION_THRESHOLD_TURNS`: Minimum turns for reflection (default: `15`)

## Production Deployment

### Docker

```dockerfile
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml .
RUN pip install -e .

COPY . .

CMD ["python", "run_server.py"]
```

```bash
docker build -t memory-service .
docker run -p 8000:8000 --env-file .env memory-service
```

### Azure Container Apps

```bash
# Build and push
docker build -t myregistry.azurecr.io/memory-service:latest .
docker push myregistry.azurecr.io/memory-service:latest

# Deploy
az containerapp create \
  --name memory-service \
  --resource-group my-rg \
  --environment my-env \
  --image myregistry.azurecr.io/memory-service:latest \
  --target-port 8000 \
  --ingress external \
  --env-vars-file .env
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: memory-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: memory-service
  template:
    metadata:
      labels:
        app: memory-service
    spec:
      containers:
      - name: memory-service
        image: myregistry.azurecr.io/memory-service:latest
        ports:
        - containerPort: 8000
        envFrom:
        - secretRef:
            name: memory-service-secrets
---
apiVersion: v1
kind: Service
metadata:
  name: memory-service
spec:
  selector:
    app: memory-service
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer
```

## Monitoring

### Key Metrics

1. **Session Pool Utilization**: `GET /stats` → `utilization`
   - Alert if > 80%

2. **Response Times**: Monitor API endpoint latencies
   - Hot session: < 50ms
   - Cold restore: < 200ms

3. **Error Rates**: Track 5xx responses
   - Target: < 0.1%

4. **Memory Usage**: Monitor container/pod memory
   - Typical: ~500MB + (sessions × 10KB)

### Logging

All operations logged with structured fields:

```
2024-01-15 10:23:45 - INFO - ✓ Hot session: user123/abc123 (0ms)
2024-01-15 10:24:12 - INFO - ✓ Cold session restored: user456/def456 (~100ms)
2024-01-15 10:25:30 - INFO - Evicted stale session: user789/ghi789 (age: 1850s)
```

## Troubleshooting

### "Session pool not initialized"

**Cause**: Service started but initialization failed.

**Fix**: Check logs for Azure OpenAI/CosmosDB connection errors. Verify credentials in `.env`.

### "Session not found"

**Cause**: Attempting to restore session that doesn't exist or was completed.

**Fix**: Start new session with `restore=false` or omit `session_id`.

### High latency on session start

**Cause**: Cold session restoration querying CosmosDB.

**Fix**: This is expected behavior. Hot sessions (in pool) are 100x faster. Increase `SESSION_TTL_MINUTES` to keep sessions in pool longer.

### Memory usage growing

**Cause**: Too many sessions in pool or TTL too long.

**Fix**: Reduce `MAX_SESSIONS` or `SESSION_TTL_MINUTES`. Monitor with `GET /stats`.

## Performance Tuning

### Session Pool Size

```python
MAX_SESSIONS = concurrent_users × 1.2  # 20% buffer
```

Example: 500 concurrent users → `MAX_SESSIONS=600`

### Session TTL

Balance between:
- **Longer TTL**: Better hit rate, more memory
- **Shorter TTL**: Less memory, more cold restores

Recommended: `30` minutes for typical chat applications

### Eviction Interval

```python
EVICTION_INTERVAL_SECONDS = SESSION_TTL_MINUTES × 60 / 2
```

Example: 30min TTL → check every 15 minutes

## Comparison: Embedded vs Remote

| Aspect | Embedded Library | Remote Service |
|--------|------------------|----------------|
| Setup | Complex (CosmosDB, OpenAI clients) | Simple (just URL) |
| Session Restore | ~100ms (CosmosDB query) | ~0ms (hot) / ~100ms (cold) |
| Resource Usage | Per-client (duplicated) | Shared (pooled) |
| Language Support | Python only | Any language |
| Deployment | Library in client | Separate microservice |
| Scaling | Scales with clients | Scales independently |

## Next Steps

1. **Run Examples**: Try `demo1_remote.py` to see it in action
2. **Integrate**: Use `CosmosMemoryProvider` in your agent
3. **Deploy**: Follow production deployment guide
4. **Monitor**: Set up alerts on `/stats` endpoint

For more details, see:
- [Main README](../README.md) - Architecture overview
- [Implementation Design](../agent_memory_implementation_design.md) - Technical details
- [Agent Framework Integration](../agent_memory_implementation_design.md#section-16-agent-framework-integration) - Context provider patterns
