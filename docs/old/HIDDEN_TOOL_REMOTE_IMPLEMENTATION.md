# Hidden Tool Injection for Remote Provider

## Summary

Extended the hidden tool injection feature (originally implemented for embedded provider) to work with the **remote memory service provider**. The agent can now autonomously search memory via HTTP calls to the service, maintaining the same clean API for users.

## Implementation Date

December 4, 2025

## Changes Made

### 1. Enhanced `cosmos_memory_provider.py` (Remote Provider)

**File:** `memory/cosmos_memory_provider.py`

**Changes:**
- Added imports for `ai_function` and `CosmosMemoryProviderConfig`
- Added `config` parameter to `__init__` method
- Updated `invoking()` to return `Context` with tools array
- Added `_create_recall_tool()` method that creates hidden tool making HTTP calls

**Key Implementation:**

```python
def _create_recall_tool(self):
    """Create hidden recall_facts tool for remote service."""
    
    # Capture closure variables
    service_url = self.service_url
    user_id = self.user_id
    session_id_getter = lambda: self.session_id
    session_started_getter = lambda: self.session_started
    client_getter = lambda: self.client
    
    @ai_function(
        name=self.config.recall_tool_name,
        description=self.config.recall_tool_description
    )
    async def recall_facts(query: str) -> str:
        """Search long-term memory via remote service."""
        if not session_started_getter():
            return "Memory not available - session not started"
        
        # Call remote service /memory/retrieve endpoint
        url = f"{service_url}/memory/retrieve"
        payload = {
            "user_id": user_id,
            "session_id": session_id_getter(),
            "query": query,
            "top_k": 5,
            "include_summaries": True,
            "include_insights": True
        }
        
        response = await client_getter().post(url, json=payload)
        response.raise_for_status()
        
        result = response.json()
        return result.get("facts", "")
    
    return recall_facts
```

**Updated `invoking()` method:**

```python
async def invoking(self, messages, **kwargs) -> Context:
    # ... existing context retrieval ...
    
    # Inject hidden recall_facts tool if enabled
    context_tools = []
    if self.config.inject_recall_tool:
        context_tools = [self._create_recall_tool()]
    
    # Return Context with instructions and tools
    return Context(
        instructions=formatted_context,
        tools=context_tools if context_tools else None
    )
```

### 2. Created Remote Demo

**File:** `demo/hidden_tool_demo_remote.py`

**Purpose:** Demonstrate hidden tool injection working with remote memory service

**Key Differences from Embedded Demo:**
- Uses `CosmosMemoryProvider` from `cosmos_memory_provider.py` (remote)
- Connects to memory service via `service_url`
- Tool makes HTTP calls to `/memory/retrieve` endpoint
- Same user-facing API and behavior

**Usage:**
```bash
# Terminal 1: Start memory service
uv run run_server.py

# Terminal 2: Run demo
uv run demo/hidden_tool_demo_remote.py
```

### 3. Updated Documentation

**File:** `demo/HIDDEN_TOOL_README.md`

**Changes:**
- Added distinction between embedded and remote providers
- Updated prerequisites for both deployment modes
- Added demo file comparison section
- Clarified that feature works with both providers

## Architecture

### Embedded Provider Flow

```
User Code
  ↓
CosmosMemoryProvider (embedded)
  ↓
invoking() → Context(tools=[recall_facts])
  ↓
recall_facts() → AgentMemoryService.search()
  ↓
Direct CosmosDB query
```

### Remote Provider Flow

```
User Code
  ↓
CosmosMemoryProvider (remote)
  ↓
invoking() → Context(tools=[recall_facts])
  ↓
recall_facts() → HTTP POST /memory/retrieve
  ↓
Memory Service
  ↓
AgentMemoryService.search()
  ↓
CosmosDB query
```

## Benefits

### 1. Consistent API

Users get the same experience regardless of deployment mode:

```python
# Embedded - Same Code
provider = CosmosMemoryProvider(
    user_id="user123",
    memory_config=memory_config,
    config=CosmosMemoryProviderConfig(inject_recall_tool=True)
)

# Remote - Same Code
provider = CosmosMemoryProvider(
    service_url="http://localhost:8000",
    user_id="user123",
    config=CosmosMemoryProviderConfig(inject_recall_tool=True)
)
```

### 2. Transparent Tool Injection

Agent code stays clean in both modes:

```python
agent = ChatAgent(
    chat_client=...,
    context_providers=[provider]
    # No explicit tools parameter!
)
```

### 3. Autonomous Agent Behavior

Agent decides when to search memory in both modes:

```
Patient: "I have a bacterial infection. Can you prescribe antibiotics?"

Agent thinking:
  → "Need to check allergies before prescribing"
  → Calls recall_facts("patient allergies medication")
  → [Embedded: Direct DB query | Remote: HTTP to service]
  → "Patient has penicillin allergy"
  → Prescribes safe alternative
```

## Configuration

### Enable/Disable

```python
from memory.provider_config import CosmosMemoryProviderConfig

config = CosmosMemoryProviderConfig(
    inject_recall_tool=True,  # Enable (default)
    recall_tool_name="recall_facts",
    recall_tool_description="Search long-term memory..."
)
```

### Customize Tool

```python
# Medical domain
config = CosmosMemoryProviderConfig(
    recall_tool_name="check_patient_history",
    recall_tool_description="Check patient's medical history and allergies"
)

# Financial domain
config = CosmosMemoryProviderConfig(
    recall_tool_name="recall_client_profile",
    recall_tool_description="Recall client's risk tolerance and goals"
)
```

## Testing

### Embedded Provider Demo

```bash
uv run demo/hidden_tool_demo.py
```

**Expected Output:**
- Session 1: Allergy disclosed
- Session 2: Routine checkup
- Session 3: Agent autonomously recalls allergy via direct DB search
- ✅ Safe prescription given

### Remote Provider Demo

```bash
# Terminal 1
uv run run_server.py

# Terminal 2
uv run demo/hidden_tool_demo_remote.py
```

**Expected Output:**
- Session 1: Allergy disclosed
- Session 2: Routine checkup
- Session 3: Agent autonomously recalls allergy via HTTP to service
- 🔍 Logs show `/memory/retrieve` endpoint called
- ✅ Safe prescription given

## Key Design Decisions

### 1. Closure Pattern for Tool Creation

**Problem:** Tool needs access to provider instance state (service_url, session_id, etc.)

**Solution:** Capture variables in closure when creating tool function:

```python
def _create_recall_tool(self):
    # Capture in closure
    service_url = self.service_url
    session_id_getter = lambda: self.session_id
    
    @ai_function(...)
    async def recall_facts(query: str) -> str:
        # Use captured variables
        url = f"{service_url}/memory/retrieve"
        session_id = session_id_getter()
        ...
```

### 2. Lazy HTTP Client Access

**Problem:** HTTP client might be closed or recreated

**Solution:** Use property getter instead of direct reference:

```python
client_getter = lambda: self.client  # Property returns active client

# In tool function
response = await client_getter().post(url, json=payload)
```

### 3. Same Config Object

**Problem:** Different config for embedded vs remote would confuse users

**Solution:** Use same `CosmosMemoryProviderConfig` for both providers:

```python
# Works for both!
config = CosmosMemoryProviderConfig(
    inject_recall_tool=True,
    recall_tool_name="recall_facts",
    recall_tool_description="..."
)
```

## Future Enhancements

### 1. Tool Call Metrics

Track tool usage in remote service:

```python
# Server-side logging
@app.post("/memory/retrieve")
async def retrieve_facts(request: RetrieveFactsRequest):
    logger.info(f"Tool call: user={request.user_id}, query={request.query}")
    # ... existing logic ...
```

### 2. Response Caching

Cache recent searches to reduce redundant calls:

```python
# In _create_recall_tool()
cache = {}  # Simple in-memory cache

async def recall_facts(query: str) -> str:
    if query in cache:
        return cache[query]
    
    result = await search_memory(query)
    cache[query] = result
    return result
```

### 3. Streaming Support

For long searches, stream results back:

```python
@app.post("/memory/retrieve/stream")
async def retrieve_facts_stream(request: RetrieveFactsRequest):
    async def generate():
        async for chunk in orchestrator.retrieve_facts_stream(request.query):
            yield f"data: {json.dumps({'chunk': chunk})}\n\n"
    
    return StreamingResponse(generate(), media_type="text/event-stream")
```

## Related Files

- `memory/cosmos_memory_provider.py` - Remote provider implementation
- `memory/cosmos_memory_provider_embedded.py` - Embedded provider (original)
- `memory/provider_config.py` - Shared configuration
- `demo/hidden_tool_demo.py` - Embedded demo
- `demo/hidden_tool_demo_remote.py` - Remote demo
- `demo/HIDDEN_TOOL_README.md` - User documentation

## Backward Compatibility

✅ **Fully backward compatible**

Existing code without `config` parameter continues to work:

```python
# Old code - still works!
provider = CosmosMemoryProvider(
    service_url="http://localhost:8000",
    user_id="user123"
)
# inject_recall_tool defaults to True via CosmosMemoryProviderConfig()
```

To disable tool injection:

```python
# Explicitly disable
provider = CosmosMemoryProvider(
    service_url="http://localhost:8000",
    user_id="user123",
    config=CosmosMemoryProviderConfig(inject_recall_tool=False)
)
```

## Conclusion

Hidden tool injection now works seamlessly with both embedded and remote providers, giving users:

- ✅ Consistent API across deployment modes
- ✅ Clean code without explicit tool definitions
- ✅ Autonomous agent memory search
- ✅ Safety-critical recall (e.g., allergy checks)
- ✅ Flexible configuration options

The feature maintains the same behavior whether memory is accessed directly (embedded) or via HTTP (remote), making it easy to switch between modes without changing agent code.
