# Overview

Agent Memory gives an agent durable memory across sessions while keeping the application-facing API simple.

## Core Components

- `AgentMemory`: the main entry point
- `MemoryOrchestrator`: coordinates retrieval, reflection, and persistence
- `MemoryKeeper`: manages active turns and session summaries
- `FactRetrieval`: searches stored memory
- `Reflection`: extracts and synthesizes longer-term insights

## Supported Usage Modes

### Direct library usage

Use `AgentMemory` directly in your own Python application.

### Agent Framework integration

Attach memory through `context_providers=[memory]`.

### Server mode

Run the FastAPI service and use `MemoryServiceClient` from local or remote apps.

## Backend Strategy

The repo is intentionally backend-pluggable:

- `sqlite` is the simplest path
- `cosmosdb` is the Azure-native document/vector path
- `azure_ai_search` is a managed search-first path
- `postgresql` is a transactional relational path with `pgvector`
