# Backend Selection

Choose the backend based on operational needs, not just feature parity.

## Quick Guidance

| Backend | Best fit | Strengths | Tradeoffs |
| --- | --- | --- | --- |
| `sqlite` | local development | zero cloud setup, fastest feedback loop | not suited for multi-instance production |
| `cosmosdb` | Azure-native app data | document store plus vector and hybrid retrieval | more Azure-specific operational model |
| `azure_ai_search` | search-first retrieval | managed vector and hybrid search with strong filtering | search service semantics rather than general DB semantics |
| `postgresql` | relational + vector workloads | SQL, transactions, and `pgvector` in one store | you own more schema and database operations |

### SQLite

Best for:

- local development
- low-friction prototypes
- simple single-node deployments

### Cosmos DB

Best for:

- Azure-native document storage
- vector and hybrid search in one managed data plane
- production use with Azure identity patterns

### Azure AI Search

Best for:

- managed search-first architecture
- native Azure AI Search vector and hybrid retrieval
- scenarios where search infrastructure is the primary store

### PostgreSQL

Best for:

- transactional relational workflows
- teams comfortable with SQL and `pgvector`
- deployments that want conventional database operations plus vector search
