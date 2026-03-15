# Azure AI Search Backend

Azure AI Search stores each memory surface in a dedicated search index and uses native vector plus hybrid retrieval.

## Configuration

```bash
AGENT_MEMORY_DB_TYPE=azure_ai_search
AZURE_AI_SEARCH_ENDPOINT=https://your-search.search.windows.net/
AZURE_AI_SEARCH_API_KEY=...
AZURE_AI_SEARCH_INDEX_PREFIX=agent-memory
```

## Operational Notes

- index creation is idempotent
- the server reuses one shared backend instance instead of recreating indexes on every request
- live direct and server/client validation paths are covered in the test suite

## Good Fit

- search-first architectures
- teams already using Azure AI Search operationally
- scenarios where hybrid search quality matters more than relational querying
