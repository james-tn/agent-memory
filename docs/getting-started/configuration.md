# Configuration

## Required Azure OpenAI Settings

Create a local `.env` file with the Azure OpenAI settings used by the library and server:

```bash
AZURE_OPENAI_ENDPOINT=https://your-resource.openai.azure.com/
AZURE_OPENAI_API_KEY=your-key
AZURE_OPENAI_API_VERSION=2025-04-01-preview

AZURE_OPENAI_REASONING_MODEL=your-chat-deployment
AZURE_OPENAI_PROCESSING_MODEL=your-processing-deployment
AZURE_OPENAI_EMB_DEPLOYMENT=text-embedding-ada-002
```

## Backend Selection

Set `AGENT_MEMORY_DB_TYPE` to one of:

- `sqlite`
- `cosmosdb`
- `azure_ai_search`
- `postgresql`

## Backend-Specific Settings

| Backend | Required settings |
| --- | --- |
| `sqlite` | `AGENT_MEMORY_DB_PATH` or constructor `db_path` |
| `cosmosdb` | `COSMOS_ENDPOINT` or `AZURE_COSMOS_CONNECTION_STRING` |
| `azure_ai_search` | `AZURE_AI_SEARCH_ENDPOINT`, `AZURE_AI_SEARCH_API_KEY` |
| `postgresql` | `POSTGRES_CONNECTION_STRING` |

## Configuration Precedence

Typical order of precedence:

1. explicit constructor arguments
2. process environment variables
3. repo `.env`
4. backend defaults where applicable

For live Azure runs in this repo:

- local `.env` remains the primary source for Azure OpenAI endpoint/key pairs
- `azd` environment outputs are the source of truth for deployed Azure Search and PostgreSQL settings
