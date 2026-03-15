# PostgreSQL Backend

PostgreSQL uses Flexible Server plus `pgvector` for memory storage and retrieval.

## Configuration

```bash
AGENT_MEMORY_DB_TYPE=postgresql
POSTGRES_CONNECTION_STRING=postgresql://...
```

## Operational Notes

- uses async PostgreSQL access through `asyncpg`
- preserves required fields on partial upserts
- supports vector and hybrid retrieval
- live direct and server/client validation paths are covered in the test suite

## Good Fit

- relational operational models
- SQL-heavy teams
- environments where PostgreSQL is already standard infrastructure
