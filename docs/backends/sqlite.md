# SQLite Backend

SQLite is the default local-development backend.

## Why Use It

- no server required
- easiest path for trying the library
- good for demos, tests, and local development

## Configuration

```bash
AGENT_MEMORY_DB_TYPE=sqlite
AGENT_MEMORY_DB_PATH=agent_memory.db
```

Or provide `db_path` directly in code.

## Notes

- the backend uses `sqlite-vec` when available
- if the vector extension is not available, it falls back to Python-based vector search
