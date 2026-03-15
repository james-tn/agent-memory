# Agent Memory

Agent Memory is a pluggable memory layer for AI agents built around Microsoft Agent Framework and Azure OpenAI.

It supports four persistence backends:

- `sqlite` for local development
- `cosmosdb` for Azure Cosmos DB
- `azure_ai_search` for managed Azure AI Search indexes
- `postgresql` for PostgreSQL Flexible Server with `pgvector`

Use this guide when you want to:

- install and configure the project
- choose the right backend
- integrate memory directly or through Agent Framework
- run the FastAPI service and Python client
- deploy Azure infrastructure with `azd`
- run live Azure validation

## Start Here

- New to the repo: go to [Getting Started > Installation](getting-started/installation.md)
- Need env vars: go to [Getting Started > Configuration](getting-started/configuration.md)
- Want code examples: go to [Usage > Direct Library Usage](usage/direct-library.md)
- Want Azure deployment: go to [Deployment > Azure Deployment](deployment/azure.md)

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

## What the System Provides

- unified `AgentMemory` API across all backends
- Agent Framework context-provider support
- session summaries and long-term insights
- vector and hybrid retrieval based on backend capability
- optional FastAPI service plus `MemoryServiceClient`

## Related Project Files

- Root project summary: [README on GitHub](https://github.com/james-tn/agent-memory/blob/main/README.md)
- Infra-focused guide: [infra/README.md on GitHub](https://github.com/james-tn/agent-memory/blob/main/infra/README.md)
- Demo-focused guide: [demo/README.md on GitHub](https://github.com/james-tn/agent-memory/blob/main/demo/README.md)
