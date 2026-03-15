# Agent Memory

Agent Memory is a Python memory layer for AI agents built around Microsoft Agent Framework and Azure OpenAI. It supports four pluggable persistence backends:

- `sqlite` for local development
- `cosmosdb` for Azure Cosmos DB with native vector and hybrid search
- `azure_ai_search` for managed Azure AI Search indexes
- `postgresql` for PostgreSQL Flexible Server with `pgvector`

Azure AI Search and PostgreSQL now have live-tested direct-library and FastAPI client/server smoke paths in addition to the existing SQLite and Cosmos support.

## Full Documentation

The repo now includes a structured user guide powered by MkDocs.

- Docs source: [`docs/`](docs/)
- Site config: [`mkdocs.yml`](mkdocs.yml)

Build it locally with:

```bash
uv sync --extra dev --extra docs
mkdocs serve
```

## Overview

| Capability | Notes |
| --- | --- |
| Unified API | `AgentMemory` exposes the same API across all backends |
| Agent Framework integration | Works as a `BaseContextProvider` via `context_providers=[...]` |
| Retrieval | Vector and hybrid search are selected per backend capability |
| Session memory | Active turns, cumulative summaries, session summaries, and long-term insights |
| Server mode | FastAPI service plus `MemoryServiceClient` for remote memory access |

## Architecture

```text
Agent / App
   |
   v
AgentMemory
   |
   +-- MemoryOrchestrator
   |    +-- MemoryKeeper
   |    +-- FactRetrieval
   |    +-- Reflection
   |
   v
Pluggable Backend
   +-- SQLite
   +-- Azure Cosmos DB
   +-- Azure AI Search
   +-- PostgreSQL + pgvector
```

## Install

```bash
uv sync --extra dev
```

`agent-framework==1.0.0rc4` is pinned in the project dependencies, and prerelease installs are enabled for `uv`.

## Required Azure OpenAI Configuration

Create a local `.env` file for the shared Azure OpenAI settings:

```bash
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_API_VERSION=2025-04-01-preview

AZURE_OPENAI_REASONING_MODEL=your-chat-deployment
AZURE_OPENAI_PROCESSING_MODEL=your-processing-deployment
AZURE_OPENAI_EMB_DEPLOYMENT=text-embedding-ada-002
```

`AZURE_OPENAI_REASONING_MODEL` and `AZURE_OPENAI_PROCESSING_MODEL` should match your actual deployment names. The current default embedding path in this repo remains `text-embedding-ada-002` with `1536` dimensions unless you override it consistently.

## Backend Selection

Set `AGENT_MEMORY_DB_TYPE` to one of:

- `sqlite`
- `cosmosdb`
- `azure_ai_search`
- `postgresql`

Backend-specific settings:

| Backend | Required settings |
| --- | --- |
| `sqlite` | `AGENT_MEMORY_DB_PATH` or constructor `db_path` |
| `cosmosdb` | `COSMOS_ENDPOINT` or `AZURE_COSMOS_CONNECTION_STRING` |
| `azure_ai_search` | `AZURE_AI_SEARCH_ENDPOINT`, `AZURE_AI_SEARCH_API_KEY`, optional `AZURE_AI_SEARCH_INDEX_PREFIX` |
| `postgresql` | `POSTGRES_CONNECTION_STRING` |

## Quick Usage

### Local SQLite

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
    print(await memory.get_context())
```

### Azure AI Search

```python
from memory import AgentMemory
from memory.db import DatabaseType

memory = AgentMemory(
    user_id="user-123",
    openai_client=client,
    db_type=DatabaseType.AZURE_AI_SEARCH,
    search_endpoint=os.environ["AZURE_AI_SEARCH_ENDPOINT"],
    search_api_key=os.environ["AZURE_AI_SEARCH_API_KEY"],
    search_index_prefix=os.getenv("AZURE_AI_SEARCH_INDEX_PREFIX", "agent-memory"),
)
```

### PostgreSQL

```python
from memory import AgentMemory
from memory.db import DatabaseType

memory = AgentMemory(
    user_id="user-123",
    openai_client=client,
    db_type=DatabaseType.POSTGRESQL,
    postgres_connection_string=os.environ["POSTGRES_CONNECTION_STRING"],
)
```

### Agent Framework Context Provider

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

### Server Mode

Start the FastAPI service:

```bash
uv run uvicorn server.main:app --host 127.0.0.1 --port 8000
```

Client usage:

```python
from client.memory_client import MemoryServiceClient

async with MemoryServiceClient("http://127.0.0.1:8000", "user-123") as client:
    ctx = await client.start_session()
    await client.store_turn("Remember I prefer train travel.", "Understood.")
    results = await client.search("travel preference", search_mode="hybrid")
    await client.end_session()
```

The server eagerly initializes its shared backend on startup so misconfiguration fails fast instead of surfacing only after the first request.

## Azure Deployment

The repo includes `azd` infrastructure for:

- Azure OpenAI
- Azure Cosmos DB
- Azure AI Search
- Azure Database for PostgreSQL Flexible Server
- Container Apps demo hosting

Quick path:

```bash
azd auth login
azd provision
```

See [infra/README.md](infra/README.md) for deployment modes, outputs, post-provision scripts, and PostgreSQL region override guidance.

## Live Testing

Focused non-live tests:

```bash
pytest -q tests/test_azure_search_backend.py tests/test_postgresql_backend.py tests/test_hybrid_search.py tests/test_server_client_compat.py
```

Live Azure smoke tests:

```bash
pytest -m live -q tests/test_live_azure_backends.py
```

The live suite covers four cloud-backed paths:

- direct `AgentMemory` with Azure AI Search
- direct `AgentMemory` with PostgreSQL
- FastAPI + `MemoryServiceClient` with Azure AI Search
- FastAPI + `MemoryServiceClient` with PostgreSQL

## Demos

The demos still center on the most approachable paths:

- SQLite for local learning and prototyping
- Cosmos DB for production-style examples
- FastAPI server mode for remote integration

See [demo/README.md](demo/README.md) for current run commands and demo-specific backend notes.

## Project Structure

```text
memory/
  core/
  db/
  providers/
server/
client/
demo/
infra/
tests/
```
