# Direct Library Usage

## SQLite Example

```python
from openai import AzureOpenAI
from memory import AgentMemory

client = AzureOpenAI(
    azure_endpoint="https://your-resource.openai.azure.com/",
    api_key="your-key",
    api_version="2025-04-01-preview",
)

async with AgentMemory(user_id="user-123", openai_client=client) as memory:
    await memory.add_turn("I like jasmine tea.", "Noted.")
    context = await memory.get_context()
    print(context)
```

## Search Example

```python
results = await memory.search(
    "travel preference",
    search_interactions=True,
    search_insights=True,
    search_summaries=True,
    search_mode="auto",
)
```

## Session Lifecycle

Typical manual flow:

1. `start_session()`
2. `add_turn(...)`
3. `get_context()` or `search(...)`
4. `end_session()`

Using `async with AgentMemory(...)` is the simplest path for local usage.
