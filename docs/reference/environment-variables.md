# Environment Variables

## Core Azure OpenAI

| Variable | Purpose |
| --- | --- |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI resource endpoint |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI API key |
| `AZURE_OPENAI_API_VERSION` | Azure OpenAI API version |
| `AZURE_OPENAI_REASONING_MODEL` | main chat/reasoning deployment |
| `AZURE_OPENAI_PROCESSING_MODEL` | processing/reflection deployment |
| `AZURE_OPENAI_EMB_DEPLOYMENT` | embedding deployment |

## Backend Selection

| Variable | Purpose |
| --- | --- |
| `AGENT_MEMORY_DB_TYPE` | backend type |
| `AGENT_MEMORY_DB_PATH` | SQLite database path |

## Cosmos DB

| Variable | Purpose |
| --- | --- |
| `COSMOS_ENDPOINT` | Cosmos endpoint |
| `AZURE_COSMOS_CONNECTION_STRING` | Cosmos connection string |
| `AZURE_COSMOS_DATABASE` | database name override |

## Azure AI Search

| Variable | Purpose |
| --- | --- |
| `AZURE_AI_SEARCH_ENDPOINT` | search endpoint |
| `AZURE_AI_SEARCH_API_KEY` | search key |
| `AZURE_AI_SEARCH_INDEX_PREFIX` | index prefix |

## PostgreSQL

| Variable | Purpose |
| --- | --- |
| `POSTGRES_CONNECTION_STRING` | PostgreSQL connection string |
| `DATABASE_URL` | alternate PostgreSQL connection string |

## Infra / `azd`

| Variable | Purpose |
| --- | --- |
| `AZURE_LOCATION` | main deployment region |
| `POSTGRES_LOCATION` | optional PostgreSQL region override |
| `POSTGRES_ADMIN_LOGIN` | PostgreSQL admin login |
| `POSTGRES_ADMIN_PASSWORD` | PostgreSQL admin password |
| `POSTGRES_SERVER_NAME_SUFFIX` | collision-recovery suffix |
