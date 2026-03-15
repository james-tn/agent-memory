# Demos

The demos are organized from simple local flows to more production-shaped integrations.

## Demo Matrix

| Demo | Primary backend | Focus |
| --- | --- | --- |
| `01_basic_memory.py` | SQLite | Smallest direct `AgentMemory` example |
| `02_agent_framework.py` | SQLite | Agent Framework context-provider integration |
| `03_agent_driven.py` | SQLite | Explicit memory-tool retrieval |
| `04_cosmosdb.py` | Cosmos DB | Production-style backend example |
| `05_server_mode.py` | Server API | FastAPI + `MemoryServiceClient` |
| `06_insight_curation.py` | SQLite | Long-term synthesis and profile evolution |
| `07_interactive_ui.py` | Server API | Streamlit UI |
| `08_itemized_insights.py` | SQLite | Bounded long-term memory behavior |
| `09_itemized_insights_cosmos.py` | Cosmos DB | Itemized insights with Cosmos persistence |

## Quick Start

```bash
uv run python demo/01_basic_memory.py
uv run python demo/02_agent_framework.py
uv run python demo/03_agent_driven.py
```

For the server-backed UI:

```bash
uv run uvicorn server.main:app --host 127.0.0.1 --port 8000
streamlit run demo/07_interactive_ui.py
```

See the repo-level demo guide at [demo/README.md on GitHub](https://github.com/james-tn/agent-memory/blob/main/demo/README.md) for more detail.
