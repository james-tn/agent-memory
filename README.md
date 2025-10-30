# 🧠 Agent Memory Service

A production-ready, enterprise-grade memory service for AI agents built on **Microsoft Agent Framework** and **Azure CosmosDB**. Provides agents with human-like memory capabilities for personalized, context-aware conversations across sessions.

---

## 🎯 Overview

The Agent Memory Service is a **standalone microservice** that enables AI agents to remember users, learn from interactions, and provide personalized experiences:

- **Microsoft Agent Framework Integration**: Native `ContextProvider` implementation for seamless memory injection
- **Multi-tier Memory Architecture**: Active turns → Cumulative summaries → Session summaries → Long-term insights
- **RESTful API**: Language-agnostic HTTP endpoints for any agent framework
- **On-Demand Memory Search**: Agents can proactively search memory via `search_memory()` tool
- **Intelligent Retrieval**: Contextual Fact Retrieval (CFR) with **hybrid search** (vector + full-text) across all memory tiers
- **Automatic Reflection**: Extract insights and patterns from conversations
- **Cost-Efficient**: Compress old context, retrieve on-demand
- **Production-Ready**: Session pooling, background tasks, health monitoring

### Why Agent Memory Service?

Traditional AI agents are stateless - they forget everything between sessions. This service enables:

✅ **Personalization** - Remember user preferences, goals, and context across sessions  
✅ **Continuity** - Maintain relationship across multiple conversations  
✅ **Efficiency** - Reduce token costs by compressing old context  
✅ **Intelligence** - Learn from patterns and improve over time  
✅ **Scale** - Shared infrastructure for multiple agents with session pooling  
✅ **Simplicity** - No memory logic in agent code, just HTTP calls

---

## 📚 Documentation

| Document | Description |
|----------|-------------|
| [agent_memory_design.md](agent_memory_design.md) | High-level conceptual design and architecture |
| [agent_memory_implementation_design.md](agent_memory_implementation_design.md) | Detailed implementation specifications |
| [README.md](README.md) | This file - setup and usage guide |

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Your AI Agent                            │
│         (Microsoft Agent Framework + CosmosMemoryProvider)   │
└────────────────┬────────────────────────────────────────────┘
                 │
                 │  HTTP/REST API
                 │
    ┌────────────▼──────────────────────────────────────────┐
    │         FastAPI Memory Service (Port 8000)            │
    │                                                         │
    │  • Session Pool (LRU Cache)  - 1000 sessions, 30min   │
    │  • Background Eviction       - Periodic cleanup        │
    │  • Health & Monitoring       - /health, /stats         │
    │                                                         │
    └────────────┬──────────────────────────────────────────┘
                 │
    ┌────────────▼──────────────┐
    │   Memory Orchestrator     │
    │                           │
    │  • Current Memory Keeper  │   ← Manages k-turn buffer
    │  • Reflection Process     │   ← Extracts insights
    │  • Fact Retrieval (CFR)   │   ← Searches history
    │                           │
    └────────────┬──────────────┘
                 │
    ┌────────────▼──────────────┐
    │   Azure CosmosDB NoSQL    │
    │  Vector + Full-Text       │
    │                           │
    │  • interactions           │   ← Conversation chunks (k-turn)
    │  • session_summaries      │   ← Session metadata + summaries
    │  • insights               │   ← Extracted learnings
    │                           │
    └───────────────────────────┘
```

### Memory Tiers

1. **Active Turns (Working Memory)**
   - Last K conversation turns kept in buffer (default K=5)
   - Immediately accessible, no retrieval needed
   - Automatically pruned when buffer fills
   - Cumulative summary maintained as turns are compressed

2. **Cumulative Summary (Within-Session Memory)**
   - Rolling summary of earlier turns in current session
   - Updated each time buffer is pruned
   - Preserves key information without full conversation replay

3. **Session Summaries (Medium-term Memory)**
   - Summary of each completed conversation session
   - Loaded at new session start for context
   - Includes key topics and extracted insights
   - Used to recall "what we talked about before"

4. **Long-term Insights (Persistent Knowledge)**
   - User profile, preferences, patterns, goals
   - Extracted via LLM-powered reflection at session end
   - Evolves over time with new interactions
   - Categorized: goals, preferences, knowledge_level, behavior_patterns, learning_progress

---

## 🚀 Quick Start

### Prerequisites

- Python 3.12+
- Azure subscription with:
  - Azure CosmosDB for NoSQL account (with vector search enabled)
  - Azure OpenAI service with:
    - gpt-5-nano/gpt-5-nanoo deployment for chat
    - text-embedding-ada-002 for embeddings
- Azure CLI (for authentication) or service principal credentials

### Installation

```bash
# Clone the repository
cd agent_memory

# Install dependencies using uv (recommended)
uv sync

# OR using pip
pip install -r requirements.txt
```

### Database Setup

Create CosmosDB containers with vector search support:

```bash
# Set environment variables
export COSMOS_ENDPOINT="https://your-account.documents.azure.com:443/"
export COSMOS_DATABASE="cosmosvector"
export AAD_TENANT_ID="your-tenant-id"
export AAD_CLIENT_ID="your-client-id"
export AAD_CLIENT_SECRET="your-client-secret"

# Run setup script
python demo/setup_cosmosdb.py
```

This creates three containers:
- **interactions**: Stores conversation chunks (k-turn windows) with embeddings
- **session_summaries**: Stores session metadata, summaries, and embeddings
- **insights**: Stores extracted user insights with embeddings

### Configuration

Create a `.env` file in the root directory:

```bash
# Azure CosmosDB
COSMOS_ENDPOINT=https://your-account.documents.azure.com:443/
COSMOS_DATABASE=cosmosvector
COSMOS_KEY=your-key  # Optional if using AAD

# AAD Authentication (if not using COSMOS_KEY)
AAD_TENANT_ID=your-tenant-id
AAD_CLIENT_ID=your-client-id
AAD_CLIENT_SECRET=your-client-secret

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-5-nano
AZURE_OPENAI_EMB_DEPLOYMENT=text-embedding-ada-002

# Memory Configuration (optional - defaults shown)
K_TURN_BUFFER=5              # Turns before pruning
M_SESSIONS_RECENT=3          # Recent sessions to load at init
ENABLE_REFLECTION=true       # Enable insight extraction

# Service Configuration (optional)
MAX_SESSIONS=1000            # Session pool size
SESSION_TTL_MINUTES=30       # Session cache TTL
EVICTION_INTERVAL_SECONDS=60 # Background cleanup interval
```

### Start the Service

```bash
# Using uv (recommended)
uv run run_server.py

# OR using Python directly
python run_server.py
```

The service starts on `http://localhost:8000` with:
- ✅ Session pooling (1000 sessions, 30-minute TTL)
- ✅ Background session eviction
- ✅ Health checks at `/health`
- ✅ Statistics at `/stats`

---

## 💻 Usage

### 🔌 Microsoft Agent Framework Integration

The `CosmosMemoryProvider` implements the Agent Framework's `ContextProvider` interface, enabling **automatic memory injection** into agent prompts with zero boilerplate.

#### How It Works

```python
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from memory.cosmos_memory_provider import CosmosMemoryProvider

# 1. Create memory provider
memory_provider = CosmosMemoryProvider(
    service_url="http://localhost:8000",
    user_id="user123",
    auto_manage_session=False
)

# 2. Add to agent as context provider
agent = ChatAgent(
    client=AzureOpenAIChatClient(...),
    context_providers=[memory_provider],  # ← Memory automatically injected!
    tools=[...]
)

# 3. Agent automatically receives context before EVERY turn
result = await agent.run("What did we discuss last time?")
```

**What Happens Under the Hood:**

1. **Before each turn**, Agent Framework calls `memory_provider.get_context()`
2. Memory service returns formatted context:
   ```
   ### Long-term Context
   - User is 35, planning retirement at 65
   - Conservative investor, prefers low-risk strategies
   - Currently has $50k saved in 401k
   
   ### Recent Sessions
   - Session abc123 (2024-10-20): Discussed employer match optimization
   
   ### Current Session Summary
   User asked about investment strategies...
   
   ### Recent Conversation
   User: I want to save for retirement
   Assistant: Great! Tell me about your situation...
   ```
3. Agent Framework **automatically injects** this context into the system prompt
4. **After each turn**, `memory_provider.store()` saves the conversation
5. Agent has full memory **without any manual context management!**

#### Complete Example

```python
import asyncio
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from memory.cosmos_memory_provider import CosmosMemoryProvider

async def main():
    # Initialize remote memory provider
    memory_provider = CosmosMemoryProvider(
        service_url="http://localhost:8000",
        user_id="user123",
        auto_manage_session=False  # Manual session control
    )
    
    # Start session explicitly
    await memory_provider._start_session()
    
    # Create agent with memory
    agent = ChatAgent(
        client=AzureOpenAIChatClient(...),
        context_providers=[memory_provider],
        tools=[...]
    )
    
    # Use agent - memory is automatically injected into prompts
    result = await agent.run("What did we discuss last time?")
    print(result.output)
    
    # Multiple turns in same session
    result = await agent.run("Can you remind me of my preferences?")
    print(result.output)
    
    # End session when done (triggers reflection)
    await memory_provider.end_session()

asyncio.run(main())
```

### Multi-Session Usage

```python
async def demo_multiple_sessions():
    user_id = "user123"
    service_url = "http://localhost:8000"
    
    # ========== SESSION 1 ==========
    print("Session 1: Initial consultation")
    memory1 = CosmosMemoryProvider(service_url=service_url, user_id=user_id, auto_manage_session=False)
    await memory1._start_session()
    
    agent = ChatAgent(client=..., context_providers=[memory1])
    await agent.run("I'm 35 and want to save for retirement. I have $50,000 saved.")
    await agent.run("I'm generally conservative with money.")
    
    await memory1.end_session()  # Stores: age, savings, risk tolerance
    
    # ========== SESSION 2 (days later) ==========
    print("Session 2: Follow-up discussion")
    memory2 = CosmosMemoryProvider(service_url=service_url, user_id=user_id, auto_manage_session=False)
    await memory2._start_session()  # Loads Session 1 summary + insights
    
    agent = ChatAgent(client=..., context_providers=[memory2])
    # Agent already knows: age=35, savings=$50k, conservative
    await agent.run("What investments would you recommend for me?")
    # Agent uses remembered profile to give personalized advice!
    
    await memory2.end_session()
```

### Direct HTTP API Usage

For non-Python agents, use HTTP directly:

```bash
# Start a session
curl -X POST http://localhost:8000/sessions/start \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user123"}'

# Response: {"session_id": "abc-123", ...}

# Store a conversation turn
curl -X POST http://localhost:8000/memory/store \
  -H "Content-Type: application/json" \
  -d '{
    "user_id": "user123",
    "session_id": "abc-123",
    "user_message": "I want to save for retirement",
    "agent_message": "Great! Tell me about your situation..."
  }'

# Get current context for prompt injection
curl -X POST http://localhost:8000/memory/context \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user123", "session_id": "abc-123"}'

# Response includes:
# - active_context: Recent turns
# - cumulative_summary: Session summary
# - insights: Long-term learnings
# - session_summaries: Previous session summaries
# - formatted_context: Ready-to-inject string

# End session (triggers reflection)
curl -X POST http://localhost:8000/sessions/end \
  -H "Content-Type: application/json" \
  -d '{"user_id": "user123", "session_id": "abc-123"}'
```

---

## 📖 Examples

### Example 1: Financial Advisor (Automatic Context)

See [`examples/demo1_financial_advisor.py`](examples/demo1_financial_advisor.py)

**Scenario:**
- Session 1: User discusses retirement planning, reveals age, savings, risk tolerance
- Session 2 (days later): User asks about investments - agent remembers profile!
- Session 3 (weeks later): Tax strategies - agent recalls all previous context

**What you'll see:**
- Session 1: Agent learns user is 35, conservative, $50k saved, goal of $60k/year at 65
- Session 2: Agent remembers profile WITHOUT re-asking! Provides personalized recommendations
- Session 3: Agent continues to build on previous knowledge

### Example 2: Medical Assistant (On-Demand Search)

See [`examples/demo4_medical_assistant.py`](examples/demo4_medical_assistant.py)

**Scenario:**
- Session 1: Patient reports penicillin allergy, prescribed Lisinopril
- Session 2: Headache complaint - agent proactively searches for allergies
- Session 3: Patient requests Amoxicillin - **agent prevents dangerous prescription!**

**What you'll see:**
- Agent **decides** when to search memory (not passive injection)
- Searches across interactions, summaries, and insights
- Prevents prescribing Amoxicillin to patient with penicillin allergy
- Critical safety check using `search_memory()` tool

**Run the demos:**

```bash
# Terminal 1: Start memory service
uv run run_server.py

# Terminal 2: Run demo
uv run python examples/demo1_financial_advisor.py
uv run python examples/demo4_medical_assistant.py
```

---

## 🔧 API Reference

### Session Management

#### POST /sessions/start
Start new session or restore existing one.

**Request:**
```json
{
  "user_id": "string",
  "session_id": "string",  // Optional - auto-generated if not provided
  "restore": true          // Attempt to restore if exists
}
```

**Response:**
```json
{
  "session_id": "abc-123",
  "user_id": "user123",
  "active_context": [],
  "cumulative_summary": "",
  "insights": [],
  "session_summaries": [],
  "formatted_context": "",
  "restored": false
}
```

#### POST /sessions/end
End session and trigger reflection to extract insights.

**Request:**
```json
{
  "user_id": "string",
  "session_id": "string"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Session ended",
  "summary_generated": true,
  "insights_count": 3,
  "turns_count": 8
}
```

### Memory Operations

#### POST /memory/store
Store a conversation turn. Triggers pruning if buffer is full.

**Request:**
```json
{
  "user_id": "string",
  "session_id": "string",
  "user_message": "string",
  "agent_message": "string"
}
```

#### POST /memory/context
Get current context for prompt injection.

**Request:**
```json
{
  "user_id": "string",
  "session_id": "string"
}
```

**Response:**
```json
{
  "active_context": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ],
  "cumulative_summary": "User is 35, planning retirement...",
  "insights": [
    {"content": "User prefers low-risk investments", "type": "longterm"}
  ],
  "session_summaries": [
    {
      "session_id": "prev-123",
      "summary": "Discussed 401k optimization",
      "timestamp": "2024-10-15T10:30:00Z",
      "topics": ["retirement", "401k"]
    }
  ],
  "formatted_context": "### Long-term Context\n..."
}
```

#### POST /memory/retrieve
On-demand semantic search across all memory tiers. Used by the `search_memory()` tool.

**What it does:**
- Searches interactions (conversation chunks) with **hybrid search** (vector + full-text)
- Searches session summaries with **hybrid search** (vector + full-text)
- Searches insights (long-term learnings) with **hybrid search** (vector + full-text)
- Uses Contextual Fact Retrieval (CFR) agent to intelligently combine results
- Returns formatted facts ready for agent consumption

**Request:**
```json
{
  "user_id": "string",
  "session_id": "string",
  "query": "string"
}
```

**Response:**
```json
{
  "query": "patient allergies medication",
  "facts": "The patient has a documented penicillin allergy that was reported during their initial visit 3 months ago. They are currently taking Lisinopril 10mg daily for blood pressure management. No other known drug allergies have been reported.",
  "count": 3
}
```

**Example Use:**
```python
# Agent tool usage
async def search_memory(self, query: str) -> str:
    """Search your past memory for relevant facts."""
    response = await self.client.post(
        f"{self.service_url}/memory/retrieve",
        json={"user_id": self.user_id, "session_id": self.session_id, "query": query}
    )
    result = response.json()
    return result["facts"]  # Returns formatted facts string
```

### Insights & Summaries

#### POST /insights
Get user insights (long-term learnings).

**Request:**
```json
{
  "user_id": "string",
  "recent_only": false
}
```

#### POST /summaries
Get session summaries for user.

**Request:**
```json
{
  "user_id": "string",
  "limit": 5
}
```

### Health & Monitoring

#### GET /health
Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "service": "agent-memory",
  "version": "1.0.0"
}
```

#### GET /stats
Session pool statistics.

**Response:**
```json
{
  "active_sessions": 42,
  "max_sessions": 1000,
  "utilization": 0.042
}
```

---

## 🎯 Key Features

### 1. Automatic Context Management

**The Service Handles:**
- ✅ Buffer management (k-turn window)
- ✅ Automatic summarization when buffer fills
- ✅ Session initialization with relevant context
- ✅ Insight extraction at session end
- ✅ Semantic retrieval from history

**Your Agent Just:**
- Calls `/memory/store` after each turn
- Calls `/memory/context` to get prompt context
- Everything else is automatic!

### 2. Progressive Summarization

**Turn 1-5 (Buffer):**
```
User: I'm 35 and want to save for retirement
Agent: Great! How much do you have saved?
User: About $50,000
Agent: What's your risk tolerance?
User: Conservative - I don't like big risks
```

**Turn 6 arrives → Pruning:**
1. Turns 1-5 summarized: "User is 35, planning retirement, $50k saved, conservative"
2. Stored as interaction chunk in CosmosDB
3. Buffer cleared, ready for turns 6-10

**Turn 10 arrives → Progressive Summary:**
```
"User is 35, planning retirement at 65, $50k saved, conservative investor.
Currently contributing 3% to 401k with 5% employer match.
Discussed increasing contribution to capture full match."
```

### 3. Reflection & Insight Extraction

**At session end, LLM analyzes and extracts:**

```json
{
  "session_summary": "Discussed retirement planning and 401k optimization...",
  "key_topics": ["retirement planning", "401k", "employer match"],
  "insights": [
    {
      "category": "preferences",
      "insight_text": "User is conservative with money and prioritizes low-risk investment strategies"
    },
    {
      "category": "goals",
      "insight_text": "User aims to retire at 65 while maintaining a $60,000-per-year lifestyle"
    },
    {
      "category": "knowledge_level",
      "insight_text": "User is new to investing and needs education on investment basics"
    }
  ],
  "has_meaningful_insights": true
}
```

These insights are:
- Stored in CosmosDB with vector embeddings
- Loaded automatically in future sessions
- Used to personalize agent responses

### 4. Cross-Session Memory

**New Session Starts:**

1. Load M=3 most recent session summaries
2. Load N=10 relevant insights for user
3. Inject into agent's initial context

**Agent Receives:**
```markdown
### Long-term Context
User Insights:
- Conservative with money, prefers low-risk investments
- Aims to retire at 65 with $60k annual lifestyle
- New to investing, needs guided education
- Underutilizing 401k employer match (3% vs 5% available)

### Recent Sessions
- Session abc123 (2024-10-20): Discussed 401k optimization and employer match
  Topics: retirement planning, 401k, employer match

- Session def456 (2024-10-15): Initial retirement planning consultation
  Topics: retirement goals, risk tolerance, savings

### Current Session Summary
(empty at start)

### Recent Conversation
(empty at start)
```

**Result:** Agent doesn't re-ask known information!

### 5. On-Demand Memory Search (Agent Tool)

**Proactive Memory Retrieval:**

Instead of passively receiving context, agents can **actively search** their memory when needed using the `search_memory()` tool:

```python
# Add search_memory as a tool
agent = ChatAgent(
    client=AzureOpenAIChatClient(...),
    tools=[
        check_drug_interactions,
        get_drug_info,
        memory.search_memory  # ← Agent can search memory proactively!
    ],
    context_providers=[memory]  # Still gets automatic context too
)
```

**How It Works:**

1. **Agent decides** when to search based on conversation context
2. Searches across all memory tiers: interactions, summaries, insights
3. Uses Contextual Fact Retrieval (CFR) with **hybrid search** (vector + full-text)
4. Returns relevant facts formatted for immediate use

**Example - Medical Safety Check:**

```
Patient: "I'd like to get Amoxicillin for this infection"

Agent thinks: "Amoxicillin is a penicillin. I should check for allergies!"

Agent calls: search_memory("patient allergies penicillin medication")

Memory returns: "Patient has documented penicillin allergy (reported 3 months ago). 
Currently taking Lisinopril for blood pressure."

Agent: "I see from your records that you have a penicillin allergy. Amoxicillin 
is a penicillin-based antibiotic and could cause a serious reaction. Let me 
recommend a safer alternative like Azithromycin instead."
```

**Benefits:**

- ✅ **Scalable**: Only retrieves what's needed, not everything every turn
- ✅ **Contextual**: Agent searches when conversation requires it
- ✅ **Safety-critical**: Perfect for medical, financial, legal scenarios
- ✅ **Tool-native**: Works like any other agent tool
- ✅ **Smart retrieval**: CFR agent uses hybrid search (vector + full-text) across all memory tiers

**Use Cases:**

- 🏥 Medical: Check allergies, drug interactions, medical history
- 💰 Financial: Recall investment preferences, risk tolerance, past decisions
- 🎓 Education: Review past lessons, identify knowledge gaps, track progress
- 🛍️ Shopping: Remember preferences, past purchases, style preferences
- ⚖️ Legal: Reference past cases, client preferences, case details

**See Demo:** [`examples/demo4_medical_assistant.py`](examples/demo4_medical_assistant.py) - Shows agent proactively preventing dangerous drug prescription by searching memory for allergies!

### 6. Session Pooling

**In-Memory LRU Cache:**
- Keeps 1000 most recent sessions in memory
- 30-minute TTL for inactive sessions
- ~5ms context retrieval for hot sessions
- Automatic persistence before eviction

**Benefits:**
- Fast response times
- Reduced CosmosDB queries
- Graceful degradation under load
- Automatic cleanup of stale sessions

---

## ⚙️ Configuration

### Environment Variables

```bash
# CosmosDB
COSMOS_ENDPOINT=https://your-account.documents.azure.com:443/
COSMOS_DATABASE=cosmosvector
COSMOS_KEY=your-key                    # Optional if using AAD
COSMOS_INTERACTIONS_CONTAINER=interactions
COSMOS_SUMMARIES_CONTAINER=session_summaries
COSMOS_INSIGHTS_CONTAINER=insights

# AAD Authentication
AAD_TENANT_ID=your-tenant-id
AAD_CLIENT_ID=your-client-id
AAD_CLIENT_SECRET=your-client-secret

# Azure OpenAI
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-api-key
AZURE_OPENAI_CHAT_DEPLOYMENT=gpt-5-nano
AZURE_OPENAI_EMB_DEPLOYMENT=text-embedding-ada-002

# Memory Settings
K_TURN_BUFFER=5                        # Buffer size
M_SESSIONS_RECENT=3                    # Recent sessions to load
N_LONGTERM_INSIGHTS=10                 # Insights to load
ENABLE_REFLECTION=true                 # Enable insight extraction

# Service Settings
HOST=0.0.0.0
PORT=8000
MAX_SESSIONS=1000                      # Session pool size
SESSION_TTL_MINUTES=30                 # Session cache TTL
EVICTION_INTERVAL_SECONDS=60          # Background cleanup interval
```

### Tuning for Scale

**For 100-500 users:**
```bash
MAX_SESSIONS=500
SESSION_TTL_MINUTES=20
K_TURN_BUFFER=5
M_SESSIONS_RECENT=3
```

**For 1000-5000 users:**
```bash
MAX_SESSIONS=2000
SESSION_TTL_MINUTES=15
K_TURN_BUFFER=5
M_SESSIONS_RECENT=2
```

**For 10000+ users:**
```bash
MAX_SESSIONS=5000
SESSION_TTL_MINUTES=10
K_TURN_BUFFER=3
M_SESSIONS_RECENT=2
# Consider horizontal scaling with load balancer
```

---

## 🧪 Testing

### Run Tests

```bash
# Unit tests
pytest tests/

# Integration tests (requires Azure resources)
pytest tests/integration/

# Run specific test
pytest tests/test_memory_keeper.py -v
```

### Debug Tools

**Query CosmosDB containers:**
```bash
python debug_query_containers.py
```

**Check specific user:**
```bash
python debug_test001.py
```

**Clear test data:**
```bash
python clear_test001.py
```

**Test context endpoint:**
```bash
python test_context_fix.py
```

### Interactive Testing

```bash
# Start service
uv run run_server.py

# In another terminal
curl http://localhost:8000/health
curl http://localhost:8000/stats
```

---

## 🏭 Production Deployment

### Docker Deployment

**Dockerfile:**
```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY . .

RUN pip install -r requirements.txt

EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

CMD ["python", "run_server.py"]
```

**Build and Run:**
```bash
# Build
docker build -t agent-memory-service .

# Run with environment file
docker run -p 8000:8000 \
  --env-file .env \
  agent-memory-service
```

### Kubernetes Deployment

**Deployment:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent-memory-service
spec:
  replicas: 3
  selector:
    matchLabels:
      app: agent-memory
  template:
    metadata:
      labels:
        app: agent-memory
    spec:
      containers:
      - name: memory-service
        image: agent-memory-service:latest
        ports:
        - containerPort: 8000
        env:
        - name: COSMOS_ENDPOINT
          valueFrom:
            secretKeyRef:
              name: azure-secrets
              key: cosmos-endpoint
        - name: AZURE_OPENAI_ENDPOINT
          valueFrom:
            secretKeyRef:
              name: azure-secrets
              key: openai-endpoint
        - name: AAD_CLIENT_ID
          valueFrom:
            secretKeyRef:
              name: azure-secrets
              key: client-id
        - name: AAD_CLIENT_SECRET
          valueFrom:
            secretKeyRef:
              name: azure-secrets
              key: client-secret
        - name: AAD_TENANT_ID
          valueFrom:
            secretKeyRef:
              name: azure-secrets
              key: tenant-id
        resources:
          requests:
            memory: "512Mi"
            cpu: "500m"
          limits:
            memory: "2Gi"
            cpu: "2000m"
        livenessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: agent-memory-service
spec:
  selector:
    app: agent-memory
  ports:
  - port: 80
    targetPort: 8000
  type: LoadBalancer
```

### Azure Container Apps

```bash
# Create resource group
az group create --name agent-memory-rg --location eastus

# Create container app environment
az containerapp env create \
  --name agent-memory-env \
  --resource-group agent-memory-rg \
  --location eastus

# Deploy container app
az containerapp create \
  --name agent-memory-service \
  --resource-group agent-memory-rg \
  --environment agent-memory-env \
  --image agent-memory-service:latest \
  --target-port 8000 \
  --ingress external \
  --min-replicas 1 \
  --max-replicas 10 \
  --cpu 1.0 \
  --memory 2.0Gi \
  --env-vars \
    COSMOS_ENDPOINT=secretref:cosmos-endpoint \
    AZURE_OPENAI_ENDPOINT=secretref:openai-endpoint
```

---

## 📊 Performance & Cost

### Performance Benchmarks

**Session Start:**
- First time (cold): ~500ms (CosmosDB query + embedding generation)
- Cached (hot): ~5ms (in-memory session pool)

**Turn Storage:**
- Without pruning: ~50ms
- With pruning (summarization): ~2-3s

**Session End (Reflection):**
- ~3-5s (LLM analysis + insight extraction + storage)

**Context Retrieval:**
- Hot session: <10ms
- Cold session: ~200ms

### Cost Estimates

**Per 1000 users, 10 sessions/month, 20 turns/session:**

**CosmosDB:**
- Storage: ~1GB/month → **$0.25/month**
- RUs: 400 RU/s provisioned → **$23/month**

**Azure OpenAI:**
- Chat (gpt-5-nano): ~200k tokens → **$6/month**
- Embeddings: ~500k tokens → **$0.10/month**

**Compute (Azure Container Apps):**
- 1 instance, 1 vCPU, 2GB RAM → **$30/month**

**Total: ~$60/month for 1000 active users (~$0.06 per user)**

### Scaling

**1,000 users:** Single instance, 400 RU/s
**10,000 users:** 3 instances, 1000 RU/s  
**100,000 users:** 10 instances, 4000 RU/s + load balancer

---

## 🔒 Security

### Authentication

**Current:**
- CosmosDB: Key-based or AAD authentication
- Azure OpenAI: API key-based
- Service: No authentication (add as needed)

**Recommended for Production:**
```python
# Add authentication middleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

security = HTTPBearer()

@app.post("/sessions/start")
async def start_session(
    request: SessionStartRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    # Validate token
    await validate_token(credentials.credentials)
    ...
```

### Data Privacy

- ✅ User data isolated by `user_id` partition key
- ✅ No cross-user data leakage
- ✅ Session IDs are UUIDs (non-guessable)
- ✅ Data encrypted at rest (CosmosDB)
- ✅ Data encrypted in transit (HTTPS)

### Best Practices

1. **Use Azure Managed Identity** in production
2. **Store secrets in Azure Key Vault**
3. **Enable CosmosDB firewall rules**
4. **Use HTTPS for all API calls**
5. **Implement rate limiting** on endpoints
6. **Add API authentication** (OAuth2, API keys)
7. **Enable audit logging**

---

## 🐛 Troubleshooting

### Common Issues

**1. "Cannot connect to server at localhost:8000"**
- Check: Is the server running? (`uv run run_server.py`)
- Check: Firewall blocking port 8000?

**2. "Session summaries return 0 results"**
- Fixed in v1.0: Session metadata was being overwritten by SessionPool
- Solution: Upgrade to latest version

**3. "Agent re-asks known information"**
- Fixed in v1.0: Remote provider wasn't including insights/summaries
- Solution: Upgrade to latest version

**4. "Memory service crashes on startup"**
- Check: CosmosDB endpoint and credentials correct?
- Check: Azure OpenAI deployment names match configuration?
- Check: Containers exist? Run `python demo/setup_cosmosdb.py`

**5. "High latency on context retrieval"**
- Check: Session pool size (`MAX_SESSIONS`)
- Check: CosmosDB RU/s provisioned
- Consider: Increasing session TTL

### Debug Mode

Enable detailed logging:

```python
import logging
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
```

### Health Monitoring

```bash
# Check service health
curl http://localhost:8000/health

# Check session pool stats
curl http://localhost:8000/stats

# Check CosmosDB metrics in Azure Portal
# - Request Units consumed
# - Document count
# - Storage size
```

---

## 🚧 Roadmap & Future Features

The following features are planned but not yet implemented. See [agent_memory_implementation_design.md](agent_memory_implementation_design.md) for detailed specifications.

### 🎯 Planned Features

#### 1. Long-term Insight Synthesis
**Status:** 🟡 Partially Implemented (foundation exists in `reflection.py`)

Currently, insights accumulate as separate documents. The design includes:
- **Two-layer reflection**: Session insights → Long-term synthesis
- **Consolidated user profile**: Single comprehensive document per user
- **Processing state tracking**: Mark insights as `processed=true` after synthesis
- **Manual trigger endpoint**: `POST /users/{user_id}/synthesize`
- **LLM-powered consolidation**: Combine related insights, resolve conflicts, deduplicate

**Benefits:**
- Reduces token costs (load one profile vs. N insights)
- Creates coherent narrative vs. bullet list
- Evolves profile over time
- Prevents unbounded growth

**Implementation needed:**
- Add `processed` field to insight documents
- Implement synthesis API endpoint
- Create synthesis prompt for LLM
- Mark source insights as processed

#### 2. CFR (Contextual Fact Retrieval) Agent
**Status:** 🔴 Not Implemented

Planned mini-agent for intelligent memory retrieval:
- **Dedicated gpt-5-nanoo-mini agent** with tools:
  - `search_interactions`: Semantic search across conversations
  - `search_insights`: Query user insights
  - `search_summaries`: Find relevant session summaries
- **Query strategy optimization**: Agent decides which tools to use
- **Result synthesis**: Combines results from multiple sources
- **Tool for main agent**: `retrieve_user_facts(query: str) -> str`

**Benefits:**
- More intelligent retrieval than simple semantic search
- Multi-source fact compilation
- Query reformulation and expansion
- Lower cost (mini model for retrieval)

**Implementation needed:**
- Create CFR agent with Agent Framework
- Implement tool functions for each search type
- Add to main agent's toolset
- Test retrieval quality

#### 3. "No-insight" Session Aggregation
**Status:** 🔴 Not Implemented

Handle trivial sessions that don't generate individual insights:
- Mark sessions with `reflection_status="no-insight"`
- Aggregate multiple "no-insight" sessions periodically
- Extract patterns across trivial interactions
- Prevent loss of incremental learning

**Benefits:**
- Captures gradual behavioral changes
- Better for casual/social conversations
- Reduces false negatives in insight extraction

#### 4. Vector Search Optimization
**Status:** 🟡 Basic Implementation

Enhance retrieval with:
- Hybrid search (vector + full-text)
- Query embedding caching
- Multi-field vector search (content + summary)
- Relevance scoring improvements

#### 5. Advanced Session Management
**Status:** 🔴 Not Implemented

- Auto-session recovery after crashes
- Session export/import for portability
- Session branching for "what-if" scenarios
- Session replay for debugging

#### 6. Observability & Analytics
**Status:** 🟡 Basic Health Checks

Planned enhancements:
- OpenTelemetry tracing
- Memory usage analytics dashboard
- Insight quality metrics
- Cost tracking per user/session
- Anomaly detection

### 📝 How to Contribute

Interested in implementing these features? See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines. The codebase has foundations for most features - they just need completion!

---

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Add tests for new functionality
4. Ensure all tests pass (`pytest`)
5. Submit a pull request

---

## 📄 License

[Your License Here]

---

## 🙏 Acknowledgments

- Built on **Microsoft Agent Framework**
- Powered by **Azure CosmosDB** and **Azure OpenAI**
- Inspired by cognitive science research on human memory systems
- Thanks to the open-source community

---

## 📞 Support

- **Documentation**: See `docs/` folder
- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions

---

**Built with ❤️ for the AI Agent community**

🚀 **Start building agents with memory today!**
