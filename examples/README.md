# CosmosDB Memory Provider Examples

This folder contains comprehensive demos showcasing the multi-tier memory capabilities of the CosmosMemoryProvider for Microsoft's Agent Framework.

## Demo Overview

### Demo 1: Financial Advisor (`demo1_financial_advisor.py`)
**Showcases:** Long-term user insights, session summaries, personalized recommendations

**Scenario:**
- Session 1: Client discusses retirement goals, reveals risk profile
- Session 2: (New thread) Investment advice - agent remembers profile
- Session 3: (New thread) Tax strategies - agent recalls all context

**Key Features:**
- ✅ Long-term user profile retention (age, goals, risk tolerance)
- ✅ Session summaries (previous consultation topics)
- ✅ Context continuity across new threads
- ✅ Personalized recommendations without re-asking questions
- ✅ Multi-tier memory: active turns → session summary → long-term insights

---

### Demo 2: Shopping Assistant (`demo2_shopping_assistant.py`)
**Showcases:** Preference learning, purchase history, product recommendations

**Scenario:**
- Session 1: Customer browses, agent learns style preferences (Nike, blue, $100-120)
- Session 2: (New thread) Personalized recommendations matching preferences
- Session 3: (New thread) Complementary items based on purchase history

**Key Features:**
- ✅ Preference learning (brand, color, budget)
- ✅ Wishlist and purchase history tracking
- ✅ Personalized product recommendations
- ✅ Complementary item suggestions
- ✅ Cross-session preference retention

---

### Demo 3: Learning Assistant (`demo3_learning_assistant.py`)
**Showcases:** Adaptive teaching, progress tracking, personalized examples

**Scenario:**
- Session 1: Initial assessment, discover learning style (visual, struggles with word problems)
- Session 2: (New thread) Adapted teaching with basketball examples
- Session 3: (New thread) Progress check, difficulty adjustment

**Key Features:**
- ✅ Learning style adaptation (visual/concrete examples)
- ✅ Interest-based personalization (basketball themes)
- ✅ Progress tracking across sessions
- ✅ Difficulty adjustment based on performance
- ✅ Encouraging, personalized teaching approach

---

### Demo 4: Medical Assistant (`demo4_medical_assistant.py`)
**Showcases:** On-demand memory search, critical safety checks, proactive memory retrieval

**Scenario:**
- Session 1: Initial visit - patient reports penicillin allergy, prescribed Lisinopril
- Session 2: Follow-up - headache complaint (agent proactively searches for allergies)
- Session 3: Urgent visit - patient requests Amoxicillin (agent prevents dangerous prescription!)

**Key Features:**
- ✅ **On-demand memory search** via `memory.search_memory()` tool
- ✅ Agent proactively searches memory when needed (vs. passive context injection)
- ✅ Critical safety checks (drug allergies, interactions)
- ✅ Contextual Fact Retrieval (CFR) uses **hybrid search** (vector + full-text) across interactions, summaries, and insights
- ✅ Real-world use case where memory search prevents harm

**Why This Demo Matters:**
- **Proactive vs Passive**: Unlike automatic context injection, the agent *decides* when to search memory
- **Safety Critical**: Demonstrates memory for high-stakes scenarios (medical, financial, legal)
- **Scalable**: Agent only searches when needed, not injecting all context every turn
- **Tool Integration**: Shows `search_memory()` as a first-class tool alongside domain tools

---

## Prerequisites

1. **Azure CLI Authentication:**
   ```bash
   az login
   ```

2. **Environment Variables** (`.env` file):
   ```
   COSMOSDB_ENDPOINT=https://your-cosmos.documents.azure.com:443/
   COSMOS_DB_NAME=your_database
   AAD_CLIENT_ID=your-client-id
   AAD_CLIENT_SECRET=your-client-secret
   AAD_TENANT_ID=your-tenant-id
   AZURE_OPENAI_ENDPOINT=https://your-openai.openai.azure.com
   AZURE_OPENAI_API_KEY=your-api-key
   AZURE_OPENAI_EMB_DEPLOYMENT=text-embedding-ada-002
   ```

3. **CosmosDB Setup:**
   Run the setup script to create required containers:
   ```bash
   python demo/setup_cosmosdb.py
   ```

## Running the Demos

Each demo is standalone and can be run independently:

```bash
# Financial Advisor
python examples/demo1_financial_advisor.py

# Shopping Assistant
python examples/demo2_shopping_assistant.py

# Learning Assistant
python examples/demo3_learning_assistant.py

# Medical Assistant (with on-demand memory search)
python examples/demo4_medical_assistant.py
```

## What Makes These Demos Special?

Unlike simple key-value memory systems, these demos showcase **multi-tier memory architecture**:

1. **Short-term Memory (Active Turns)**
   - Recent conversation context (last 3-5 exchanges)
   - Automatically pruned as conversation grows

2. **Mid-term Memory (Session Summaries)**
   - Summarized topics from recent sessions
   - Retrieved when starting new conversations
   - Shows what was discussed 1 week ago, 1 month ago, etc.

3. **Long-term Memory (User Insights)**
   - Persistent user profile and preferences
   - Extracted through AI-powered reflection
   - Categorized by type (preferences, goals, constraints, relationships)

## Architecture Highlights

```
┌─────────────────────────────────────────────────────────────┐
│  Agent Framework (Microsoft's Agent Framework)              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  ContextProvider Interface                            │  │
│  │  • thread_created() → Start session                   │  │
│  │  • invoking() → Inject context before AI call         │  │
│  │  • invoked() → Store conversation after AI responds   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  CosmosMemoryProvider                                       │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Memory Orchestrator                                  │  │
│  │  • Manages 3-tier memory architecture                 │  │
│  │  • Coordinates storage, retrieval, summarization      │  │
│  │  • Triggers AI-powered reflection                     │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│  Azure CosmosDB (Vector-enabled)                            │
│  • interactions container (turn-by-turn storage)            │
│  • session_summaries (mid-term memory)                      │
│  • insights (long-term user profile)                        │
│  • Vector search for semantic retrieval                     │
└─────────────────────────────────────────────────────────────┘
```

## Memory Flow Example

**Session 1:**
```
User: "I'm 35 and want to retire at 65"
→ Stored in active buffer
→ After session: Summarized and stored
→ AI extracts insight: "User goal: Retire at 65, Current age: 35"
```

**Session 2 (New Thread):**
```
invoking() is called
→ Retrieves long-term insights: "35 years old, retire at 65"
→ Retrieves session summary: "Previously discussed retirement planning"
→ Injects as context to AI
→ AI knows user without being told again
```

## Customization

Each demo can be customized via `CosmosMemoryProviderConfig`:

```python
config = CosmosMemoryProviderConfig(
    include_longterm_insights=True,      # Include user profile
    include_recent_sessions=True,        # Include past session summaries
    include_cumulative_summary=True,     # Include current session summary
    include_active_turns=False,          # Don't duplicate thread history
    num_recent_sessions=3,               # How many past sessions to include
    trigger_reflection_on_end=True,      # Extract insights after each session
    context_injection_mode="messages",   # "messages" or "instructions"
)
```

## Troubleshooting

### "Cosmos DB firewall blocked"
Enable public network access or add your IP:
```bash
az cosmosdb update --name your-cosmos --resource-group your-rg --enable-public-network true
```

### "Module not found: agent_framework"
Install the agent framework:
```bash
cd agent-framework/python
pip install -e packages/core packages/azure-ai
```

### "No long-term insights found"
This is normal for first-time users. Insights are generated after completing at least one session with `trigger_reflection_on_end=True`.

## License

Copyright (c) Microsoft Corporation. All rights reserved.
Licensed under the MIT License.
