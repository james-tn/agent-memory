# Demo Guide

These demos are still arranged from simple local flows to more production-shaped integrations. The overall product now supports SQLite, Cosmos DB, Azure AI Search, and PostgreSQL, but the demos intentionally focus on the clearest teaching paths instead of trying to show every backend in every script.

## Demo Matrix

| Demo | Primary backend | Focus |
| --- | --- | --- |
| `01_basic_memory.py` | SQLite | Smallest direct `AgentMemory` example |
| `02_agent_framework.py` | SQLite | Agent Framework `context_providers=[...]` integration |
| `03_agent_driven.py` | SQLite | Explicit memory-tool retrieval |
| `04_cosmosdb.py` | Cosmos DB | Production-style backend example |
| `05_server_mode.py` | Server API | FastAPI + `MemoryServiceClient` flow |
| `06_insight_curation.py` | SQLite | Long-term synthesis and profile evolution |
| `07_interactive_ui.py` | Server API | Streamlit UI against the memory service |
| `08_itemized_insights.py` | SQLite | Bounded long-term memory behavior |
| `09_itemized_insights_cosmos.py` | Cosmos DB | Itemized insights with Cosmos persistence |

## Quick Start

```bash
uv run python demo/01_basic_memory.py
uv run python demo/02_agent_framework.py
uv run python demo/03_agent_driven.py
```

## Backend Notes

- Demos `01`, `02`, `03`, `06`, and `08` are local SQLite-first examples.
- Demos `04` and `09` assume Cosmos DB is configured.
- Demos `05` and `07` go through the FastAPI service, so the server backend can be switched with `AGENT_MEMORY_DB_TYPE`.
- Azure AI Search and PostgreSQL are primarily exercised today through the shared library API, server mode, and the live smoke suite rather than dedicated demo scripts.

## Server-Backed Demos

Start the service first:

```bash
uv run uvicorn server.main:app --host 127.0.0.1 --port 8000
```

Then run:

```bash
uv run python demo/05_server_mode.py
streamlit run demo/07_interactive_ui.py
```

To point the server at a different backend:

```bash
export AGENT_MEMORY_DB_TYPE=azure_ai_search
export AZURE_AI_SEARCH_ENDPOINT=...
export AZURE_AI_SEARCH_API_KEY=...
uv run uvicorn server.main:app --host 127.0.0.1 --port 8000
```

Or:

```bash
export AGENT_MEMORY_DB_TYPE=postgresql
export POSTGRES_CONNECTION_STRING=...
uv run uvicorn server.main:app --host 127.0.0.1 --port 8000
```

## Cosmos Demos

For Cosmos-backed demos, configure either:

- `COSMOS_ENDPOINT` with Azure identity auth, or
- `AZURE_COSMOS_CONNECTION_STRING`

See [infra/README.md](../infra/README.md) for the Azure deployment path.

## Azure OpenAI Settings

All demos expect the usual Azure OpenAI variables:

```bash
AZURE_OPENAI_ENDPOINT=...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_API_VERSION=2025-04-01-preview
AZURE_OPENAI_REASONING_MODEL=...
AZURE_OPENAI_PROCESSING_MODEL=...
AZURE_OPENAI_EMB_DEPLOYMENT=text-embedding-ada-002
```

## Practical Tips

- Use `streamlit run demo/07_interactive_ui.py` instead of `python demo/07_interactive_ui.py`.
- Server demos are the easiest way to exercise Azure AI Search or PostgreSQL without editing demo code.
- If you want cloud-backed end-to-end validation instead of a tutorial demo, run `pytest -m live -q tests/test_live_azure_backends.py`.
