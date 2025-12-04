# Hidden Tool Injection Demos

This directory contains demonstrations of the **hidden tool injection** feature in `CosmosMemoryProvider`.

## Quick Start

### Prerequisites

1. **Azure CLI Authentication:**
   ```bash
   # Log in to Azure CLI (demos use AzureCliCredential)
   az login
   ```

2. **Environment Setup:**
   
   If you already have a `.env` file in the root directory with working Azure credentials (from running other demos), you're all set!
   
   If not, copy the template and fill in your credentials:
   ```bash
   # Copy the demo environment template
   cp demo/.env.example .env
   
   # Edit .env and fill in your Azure credentials
   ```

3. **Required Environment Variables:**
   
   **For Embedded Provider Demos:**
   - `COSMOS_ENDPOINT` - Your Cosmos DB endpoint (e.g., https://your-account.documents.azure.com:443/)
   - `AZURE_OPENAI_ENDPOINT` - Your Azure OpenAI endpoint
   - `AZURE_OPENAI_API_KEY` - Your Azure OpenAI API key
   - `AZURE_OPENAI_REASONING_MODEL` - Model for reasoning (e.g., gpt-4o)
   - `AZURE_OPENAI_PROCESSING_MODEL` - Model for processing (e.g., gpt-4o)
   
   **For Remote Service Demos:**
   - `MEMORY_SERVICE_URL` - Memory service endpoint (default: http://localhost:8000)
   - `AZURE_OPENAI_REASONING_MODEL` - Model for reasoning (e.g., gpt-4o)
   
   **Optional:**
   - `COSMOS_KEY` - Cosmos DB key (if not provided, uses DefaultAzureCredential)
   - `AZURE_COSMOS_DATABASE_NAME` - Database name (default: agent_memory_db)

4. **Run Demos:**
   
   **Embedded Provider (Direct CosmosDB Access):**
   ```bash
   # Medical safety demo (embedded)
   uv run demo/hidden_tool_demo.py
   
   # Comparison demo (embedded)
   uv run demo/comparison_tool_injection_demo.py
   ```
   
   **Remote Service (Requires Memory Service Running):**
   ```bash
   # Start memory service (in separate terminal)
   uv run run_server.py
   
   # Medical safety demo (remote)
   uv run demo/hidden_tool_demo_remote.py
   ```

## Overview

The hidden tool injection feature automatically injects a `recall_facts` tool into agents using `CosmosMemoryProvider`. The agent can autonomously search long-term memory when needed, **without the user explicitly defining the tool**.

**Works with BOTH providers:**
- ✅ **Embedded Provider** (`CosmosMemoryProvider` from `cosmos_memory_provider_embedded.py`)
  - Direct CosmosDB access via Python SDK
  - Tool searches memory locally
  
- ✅ **Remote Provider** (`CosmosMemoryProvider` from `cosmos_memory_provider.py`)
  - Connects to memory service via HTTP
  - Tool calls `/memory/retrieve` endpoint on server
  - Requires memory service running

### Key Features

- ✅ Tool is injected automatically via `ContextProvider.invoking()`
- ✅ User doesn't define the tool in their code
- ✅ Agent decides when to call it based on conversation context
- ✅ Works seamlessly with Agent Framework's tool calling
- ✅ Enabled by default (can be disabled via config)
- ✅ Configurable tool name and description
- ✅ **Same API for both embedded and remote providers**

## Architecture

```python
# How it works:
CosmosMemoryProvider.invoking()
    ↓
Context(
    messages=[...],           # Passive context injection
    tools=[recall_facts]      # Hidden tool injection ← NEW!
)
    ↓
Agent Framework
    ↓
Agent has recall_facts available
    ↓
Agent autonomously calls it when needed
```

## Configuration

### Enable/Disable Hidden Tool

```python
from memory.provider_config import CosmosMemoryProviderConfig

config = CosmosMemoryProviderConfig(
    memory_config=memory_config,
    inject_recall_tool=True,  # Enable (default: True)
    recall_tool_name="recall_facts",  # Customize name
    recall_tool_description="..."  # Customize description
)
```

### User Code (No Explicit Tools!)

```python
from agent_framework import ChatAgent
from memory.cosmos_memory_provider_embedded import CosmosMemoryProvider

# Create provider
provider = CosmosMemoryProvider(
    user_id="user123",
    memory_config=memory_config,
    config=provider_config  # inject_recall_tool=True by default
)

# Create agent WITHOUT defining any tools
agent = ChatAgent(
    chat_client=chat_client,
    instructions="You are a helpful assistant",
    context_providers=[provider]  # ← recall_facts injected automatically
    # NOTE: No tools parameter!
)

# Agent automatically has recall_facts available
result = await agent.run("What did we discuss last month?")
# Behind the scenes: Agent may call recall_facts("discussions last month")
```

## Demos

### 1. `hidden_tool_demo.py`

**Purpose:** Show the hidden tool in action with a medical safety scenario.

**Scenario:**
- Session 1: Patient mentions severe penicillin allergy
- Session 2: General checkup (no medication discussion)
- Session 3: Patient needs antibiotics
- Agent autonomously calls `recall_facts` to check allergies before prescribing

**Run:**
```bash
python demo/hidden_tool_demo.py
```

**Expected Output:**
```
🏥 Session 3: Bacterial Infection
👤 Patient: Can you prescribe antibiotics?
  ℹ️  [Agent autonomously called tools: ['recall_facts']]
👨‍⚕️ Doctor: I see you're allergic to penicillin. I'll prescribe azithromycin instead.
```

---

### 2. `comparison_tool_injection_demo.py`

**Purpose:** Compare agent behavior with and without hidden tool injection.

**Scenario:**
- Session 1: Client sets strict risk tolerance (max 5% loss)
- Session 2-3: Other topics (pushes Session 1 out of recent context)
- Session 4: Agent needs to make investment recommendation

**Run:**
```bash
python demo/comparison_tool_injection_demo.py
```

**Expected Results:**

| Scenario | Tool Enabled | Agent Behavior | Result |
|----------|-------------|----------------|--------|
| A | ❌ No | Only has Session 3 in passive context | Generic recommendation, ignores constraint |
| B | ✅ Yes | Calls `recall_facts("risk tolerance")` | Personalized, constraint-aware recommendation |

---

## How It Works Internally

### `CosmosMemoryProvider._create_recall_tool()`

Creates the hidden tool using the `@ai_function` decorator:

```python
@ai_function(name="recall_facts", description="...")
async def recall_facts(query: str) -> str:
    """Search long-term memory for relevant information."""
    return await memory.search(
        query,
        include_summaries=True,
        include_insights=True
    )
```

### `CosmosMemoryProvider.invoking()`

Injects the tool into the context before agent invocation:

```python
async def invoking(self, messages, **kwargs) -> Context:
    # 1. Build passive context (existing)
    context_messages = self._build_context_messages()
    
    # 2. Inject hidden tool (NEW)
    context_tools = []
    if self.config.inject_recall_tool:
        context_tools = [self._create_recall_tool()]
    
    return Context(
        messages=context_messages,
        tools=context_tools  # ← Injected transparently
    )
```

## Benefits

### For Users

- **Cleaner Code**: No need to define `search_memory` function explicitly
- **Zero Boilerplate**: Memory search capability added with just config flag
- **Transparent**: Agent Framework handles tool calling automatically
- **Flexible**: Can enable/disable per use case

### For Agents

- **Autonomous**: Agent decides when to search (intelligent behavior)
- **Proactive**: Can retrieve information beyond passive context
- **Safe**: Critical information (allergies, constraints) always accessible
- **Efficient**: Only searches when needed (vs. always retrieving)

## Comparison with Other Approaches

### 1. Passive Context Injection (Existing)

**How it works:** Load recent sessions at initialization, inject as messages.

```python
config = CosmosMemoryProviderConfig(
    include_recent_sessions=True,
    num_recent_sessions=2  # Load 2 recent sessions
)
```

**Pros:**
- ✅ Fast (no LLM calls)
- ✅ All recent context available upfront

**Cons:**
- ❌ Fixed context (can't adapt mid-conversation)
- ❌ May miss older but relevant information
- ❌ Context bloat for irrelevant sessions

---

### 2. Explicit Tool Definition (Previous Approach)

**How it works:** User defines `search_memory` tool manually.

```python
@ai_function
async def search_memory(query: str) -> str:
    return await orchestrator.retrieve_facts(query)

agent = ChatAgent(
    chat_client=chat_client,
    tools=[search_memory]  # User defines explicitly
)
```

**Pros:**
- ✅ Full control over tool behavior
- ✅ Transparent to user (they see the tool)

**Cons:**
- ❌ More boilerplate code
- ❌ User must understand orchestrator API
- ❌ Less integrated with provider pattern

---

### 3. Hidden Tool Injection (This Feature) ⭐

**How it works:** Provider automatically injects tool.

```python
config = CosmosMemoryProviderConfig(
    inject_recall_tool=True  # Default: True
)

agent = ChatAgent(
    chat_client=chat_client,
    context_providers=[provider]  # Tool injected automatically
)
```

**Pros:**
- ✅ Zero boilerplate
- ✅ Agent-driven (intelligent search timing)
- ✅ Integrated with Agent Framework
- ✅ Configurable (can disable if needed)
- ✅ Clean user code

**Cons:**
- ❌ Less explicit (tool "hidden" from user code)
- ❌ Requires Agent Framework tool calling support

---

## Recommended Usage Patterns

### Pattern 1: Medical/Financial Safety (High Stakes)

**Use Case:** Prevent errors by ensuring critical information is always retrievable.

```python
config = CosmosMemoryProviderConfig(
    inject_recall_tool=True,  # MUST enable
    include_recent_sessions=True,
    num_recent_sessions=1  # Only load most recent
)
```

**Why:**
- Agent can search for allergies, risk tolerance, constraints
- Reduces risk of missing critical information
- Agent autonomously searches before making recommendations

---

### Pattern 2: General Assistance (Low Stakes)

**Use Case:** Helpful but not critical memory access.

```python
config = CosmosMemoryProviderConfig(
    inject_recall_tool=True,  # Enable for flexibility
    include_recent_sessions=True,
    num_recent_sessions=2  # More passive context
)
```

**Why:**
- Passive context handles most queries
- Tool available as fallback for older information
- Balanced approach (passive + active)

---

### Pattern 3: Cost-Sensitive (Optimize LLM Calls)

**Use Case:** Minimize tool calls to reduce costs.

```python
config = CosmosMemoryProviderConfig(
    inject_recall_tool=False,  # Disable to prevent searches
    include_recent_sessions=True,
    num_recent_sessions=3  # Load more passive context
)
```

**Why:**
- No tool calls = no extra LLM inferences
- Rely entirely on passive context
- Suitable for simple Q&A with recent context

---

## Best Practices

### 1. Tool Description Matters

Make the description clear so the agent knows when to use it:

```python
config = CosmosMemoryProviderConfig(
    recall_tool_description=(
        "Search long-term memory when you need information about the user's "
        "past preferences, constraints, or history that isn't in recent messages. "
        "Examples: allergies, risk tolerance, past decisions."
    )
)
```

### 2. Combine with Passive Context

Best results come from hybrid approach:

```python
config = CosmosMemoryProviderConfig(
    include_recent_sessions=True,  # Passive context
    num_recent_sessions=1,         # Only most recent
    inject_recall_tool=True        # Active search for older data
)
```

**Result:** Fast (passive) + Flexible (active)

### 3. Monitor Tool Usage

Track when agent calls the tool to optimize configuration:

```python
result = await agent.run(message)
if result.function_calls:
    print(f"Agent searched memory: {result.function_calls}")
```

### 4. Customize Per Domain

Adjust tool name/description for specific domains:

```python
# Medical domain
config = CosmosMemoryProviderConfig(
    recall_tool_name="check_patient_history",
    recall_tool_description="Check patient's medical history, allergies, and past treatments"
)

# Financial domain
config = CosmosMemoryProviderConfig(
    recall_tool_name="recall_client_profile",
    recall_tool_description="Recall client's risk tolerance, goals, and investment constraints"
)
```

---

## Troubleshooting

### Tool Not Being Called

**Problem:** Agent doesn't call `recall_facts` when expected.

**Solutions:**
1. Check tool description - make it more specific
2. Update agent instructions to mention tool usage
3. Verify `inject_recall_tool=True`
4. Check if information is already in passive context (no search needed)

### Too Many Tool Calls

**Problem:** Agent calls tool excessively, increasing costs.

**Solutions:**
1. Increase `num_recent_sessions` (more passive context)
2. Update tool description to be more restrictive
3. Consider disabling tool for cost-sensitive scenarios
4. Add caching to reduce redundant searches

### Tool Not Available

**Problem:** `ContextProvider has no attribute 'inject_recall_tool'`

**Solutions:**
1. Ensure you're using `CosmosMemoryProviderConfig`
2. Update to latest version with hidden tool support
3. Check config initialization

---

## Future Enhancements

Potential improvements for future versions:

1. **Confidence-based triggering**: Auto-inject tool only when confidence is low
2. **Adaptive tool injection**: Enable/disable based on conversation patterns
3. **Multi-tool injection**: Inject multiple specialized tools (recall_insights, recall_summaries)
4. **Tool call analytics**: Built-in tracking of tool usage patterns
5. **Smart caching**: Cache search results to reduce redundant LLM calls

---

## Demo Files

### `hidden_tool_demo.py` (Embedded Provider)

Medical safety demonstration using **embedded provider** (direct CosmosDB access):

- **Scenario:** Patient with penicillin allergy across 3 sessions
- **Session 1:** Allergy disclosure
- **Session 2:** Routine checkup (no allergy discussion)
- **Session 3:** Agent autonomously recalls allergy when prescribing antibiotics
- **Result:** Safe prescription based on recalled allergy information

**Run:**
```bash
uv run demo/hidden_tool_demo.py
```

**Requirements:**
- Direct CosmosDB credentials
- Azure OpenAI credentials
- No memory service needed

### `hidden_tool_demo_remote.py` (Remote Provider)

Same medical safety demonstration using **remote provider** (HTTP to memory service):

- **Same scenario** as embedded demo
- **Different provider:** Uses HTTP client to communicate with memory service
- **Demonstrates:** Hidden tool injection works identically with remote service
- **Tool behavior:** `recall_facts` makes HTTP POST to `/memory/retrieve` endpoint

**Run:**
```bash
# Terminal 1: Start memory service
uv run run_server.py

# Terminal 2: Run demo
uv run demo/hidden_tool_demo_remote.py
```

**Requirements:**
- Memory service running
- Azure CLI authentication (`az login`)
- Service URL in .env (default: http://localhost:8000)

### `comparison_tool_injection_demo.py` (Embedded Provider)

Side-by-side comparison showing impact of hidden tool injection:

- **Scenario A (Without Tool):** Agent can only use passive context
- **Scenario B (With Hidden Tool):** Agent can autonomously search memory
- **Result:** Clear demonstration of improved recall with tool injection

**Run:**
```bash
uv run demo/comparison_tool_injection_demo.py
```

---

## Related Documentation

- [Auto-Enrichment Investigation](../docs/AUTO_ENRICHMENT_CONTEXT_PROVIDER_INVESTIGATION.md)
- [Context Provider Architecture](../docs/IMPLEMENTATION_SUMMARY.md)
- [Agent Framework Integration](../README.md#-microsoft-agent-framework-integration)

---

## Questions?

For issues or questions about hidden tool injection:
1. Check configuration settings
2. Review demo code for examples
3. Verify Agent Framework version supports tool injection via Context
