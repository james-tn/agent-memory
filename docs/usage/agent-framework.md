# Agent Framework Integration

Agent Memory can be used as a Microsoft Agent Framework context provider.

## Basic Pattern

```python
from agent_framework import Agent
from agent_framework.azure import AzureOpenAIChatClient
from memory import AgentMemory

memory = AgentMemory(user_id="user-123", openai_client=client)

agent = Agent(
    client=AzureOpenAIChatClient(
        endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
        api_key=os.environ["AZURE_OPENAI_API_KEY"],
        api_version=os.environ["AZURE_OPENAI_API_VERSION"],
        deployment_name=os.environ["AZURE_OPENAI_REASONING_MODEL"],
    ),
    instructions="You are a helpful assistant.",
    context_providers=[memory],
)
```

## What Memory Does

- injects memory context before each run
- stores turns after each run
- can enrich context with retrieved facts when enabled

## When to Use Tool-Driven Retrieval

Use explicit memory tools when:

- you want retrieval to be observable and auditable
- memory lookups should happen only under certain agent decisions
- you want the agent to control when to search versus when to rely on injected context
