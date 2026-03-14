# Agent Memory Service — Code Review & Improvement Recommendations

## Context

A thorough code review of the Agent Memory Service identified 40+ issues across the core library, database backends, server, client, agent, and demos. This document presents prioritized, actionable recommendations organized by severity. The goal is to improve correctness, reliability, security, and maintainability.

---

## CRITICAL — Bugs and vulnerabilities that cause incorrect behavior or security risk

### C1. SQLite filtered vector search produces invalid SQL (broken feature)
**Files:** `memory/db/sqlite_backend.py` lines 541-613
- When `filters` are provided, the query generates two `WHERE` clauses (`WHERE t.user_id = ? WHERE v.content_vector MATCH ?`), which is invalid SQL
- Every filtered vector search silently falls back to `_vector_search_fallback`, which loads ALL documents into memory for O(n) cosine similarity
- **Fix:** Change the second `WHERE` to `AND` when filter_clause is non-empty

### C2. SQLite SQL injection via unvalidated filter column names
**Files:** `memory/db/sqlite_backend.py` lines 490-497, 574-578, 632
- Filter keys from the `filters` dict are interpolated directly into SQL: `f"{key} = ?"` — values are parameterized but column names are not
- If filters ever originate from user input (e.g., via the REST API), this is exploitable
- **Fix:** Validate filter keys against an allowlist of valid column names per container type

### C3. Embedding model default mismatch between config layers
**Files:** `memory/core/agent_memory.py` lines 70-71, `memory/core/orchestrator.py` lines 45-46
- `AgentMemoryConfig` defaults to `text-embedding-ada-002` / 1536 dimensions
- `OrchestratorConfig` defaults to `text-embedding-3-large` / 3072 dimensions
- If `OrchestratorConfig` is used directly (bypassing `AgentMemoryConfig`), vector dimensions won't match, causing silent data corruption
- **Fix:** Align defaults across both config classes

### C4. CosmosDB uses synchronous SDK inside async methods
**File:** `memory/db/cosmos_backend.py`
- All methods are `async def` but call synchronous `azure.cosmos.CosmosClient`, blocking the event loop
- In a FastAPI server with concurrent requests, this serializes all DB access
- **Fix:** Migrate to `azure.cosmos.aio.CosmosClient`

---

## HIGH — Significant functional problems, resource leaks, or degraded reliability

### H1. `end_session()` destroys the entire AgentMemory instance
**File:** `memory/core/agent_memory.py` lines 361-368
- Calls `close()` which nulls the orchestrator and DB connection — cannot start a new session without full re-initialization
- **Fix:** Separate session lifecycle from instance lifecycle; only reset session state in `end_session()`

### H2. Background tasks can silently fail after database close
**File:** `memory/core/memory_keeper.py` lines 283-295
- `maybe_prune()` spawns `asyncio.create_task()` for interaction processing; if `close()` races with these tasks, writes fail silently (`return_exceptions=True` swallows errors)
- **Fix:** Log gathered exceptions; ensure `close()` waits for pending tasks; add a shutdown flag

### H3. Adapter layer uses deprecated `asyncio.get_event_loop().run_until_complete()`
**File:** `memory/db/adapters.py` lines 42, 57, 72, 120, 170, 217, 230, 289
- Deprecated in Python 3.10+; raises `RuntimeError` if called from within a running event loop (i.e., from FastAPI)
- **Fix:** Remove sync adapter methods or use `asyncio.run()` in a thread

### H4. `get_context()` is synchronous while the rest of the API is async
**File:** `memory/core/agent_memory.py` lines 370-391
- Also bypasses the orchestrator to access `_memory_keeper` directly
- **Fix:** Make async; route through orchestrator's public interface

### H5. CosmosDB `vector_search` hardcodes field subset — misses fields
**File:** `memory/db/cosmos_backend.py` lines 303-309
- Returns only a fixed set of fields; misses `date_added`, `last_accessed`, `access_count`, `confidence`, `importance`, etc.
- SQLite returns `SELECT *` — so backends return different data shapes
- **Fix:** Use `SELECT *` or build field list per ContainerType

### H6. CosmosDB bare `except Exception` swallows all errors
**File:** `memory/db/cosmos_backend.py` lines 204-211, 220-229
- `get_by_id()` and `delete()` catch all exceptions and return None/False — hides auth errors, timeouts, throttling
- **Fix:** Catch only `CosmosResourceNotFoundError`; let other exceptions propagate

### H7. Server session pool holds lock during LLM calls on eviction
**File:** `server/main.py` lines 241-258
- `_evict_oldest()` calls `end_session()` (which involves LLM calls) while holding the async lock, blocking all other session operations
- **Fix:** Extract eviction candidate under lock, release lock, then perform slow cleanup

### H8. Server creates temporary sessions for every read-only request
**File:** `server/main.py` lines 521-592
- `/search`, `/users/{user_id}/insights`, `/users/{user_id}/sessions` all create and tear down a full AgentMemory session per request
- **Fix:** Add a lightweight read-only query path that uses a shared DB connection pool

### H9. SQLite `batch_upsert` does individual commits per document
**File:** `memory/db/sqlite_backend.py` lines 402-413
- **Fix:** Wrap entire batch in a single transaction

### H10. SQLite `_update_vector_index` DELETE+INSERT not transactional
**File:** `memory/db/sqlite_backend.py` lines 358-400
- Crash between DELETE and INSERT loses the vector index entry
- **Fix:** Wrap in a single transaction; bundle commit with main upsert

---

## MEDIUM — Code quality, maintainability, and minor functional issues

### M1. `datetime.utcnow()` deprecated throughout (project requires Python 3.12+)
**Files:** All core modules, server/main.py
- **Fix:** Replace with `datetime.now(datetime.timezone.utc)`

### M2. `restore` parameter accepted but never implemented
**Files:** `agent_memory.py`, `memory_client.py`, `server/main.py`
- **Fix:** Either implement session restore or remove the parameter

### M3. Pydantic models defined but never used by database layer
**File:** `memory/models.py`
- Models diverge from actual DB schema; DB layer uses raw dicts with no validation
- **Fix:** Update models to match schema; use for validation in upsert

### M4. Duplicate `SessionInitContext` definition
**Files:** `memory/models.py` line 93, `memory/core/memory_keeper.py` line 69
- **Fix:** Keep one source of truth

### M5. Embedding provider lacks input validation and resilience
**File:** `memory/providers/embedding.py`
- No empty-text validation, no retry logic, no batch size limits, Azure deployment name check broken
- **Fix:** Add validation, retry with backoff, batch chunking

### M6. `LONGTERM_SYNTHESIS_PROMPT` hardcoded for financial advisor domain
**File:** `memory/prompts.py` lines 77-102
- General-purpose system uses finance-specific prompt; a generic version exists but isn't used
- Unused `SESSION_REFLECTION_PROMPT` also present
- **Fix:** Route synthesis through the generic prompt; remove dead prompts

### M7. Missing `source_session_ids` in SQLite JSON deserialization
**File:** `memory/db/sqlite_backend.py` line 280
- **Fix:** Add `"source_session_ids"` to `json_fields` in `_row_to_dict()`

### M8. CosmosDB `close()` doesn't close the client
**File:** `memory/db/cosmos_backend.py` lines 136-142

### M9. Server lacks authentication/authorization
**File:** `server/main.py` — all endpoints publicly accessible

### M10. Agent context manager entered but never exited (resource leak)
**File:** `agent/single_agent.py` line 68

### M11. `load_dotenv()` at module import in CosmosDB backend (side effect)
**File:** `memory/db/cosmos_backend.py` line 33

### M12. Server uses POST for read-only `/sessions/context` endpoint
**File:** `server/main.py` line 452

### M13. Backend abstraction returns different data shapes from same operations
**Files:** `sqlite_backend.py`, `cosmos_backend.py`

---

## LOW — Minor code quality and documentation issues

- **L1.** Unbounded `chat_history` growth in `agent/base_agent.py`
- **L2.** Typo: "hallunicate" → "hallucinate" in `agent/single_agent.py` line 56
- **L3.** Access to private Agent Framework API `_local_mcp_tools` in `agent/single_agent.py` line 110
- **L4.** Client lacks retry logic and per-operation timeouts (`client/memory_client.py`)
- **L5.** Client HTTP client can leak if not used with context manager
- **L6.** `ServerConfig` defined but mostly not used by `server/main.py`
- **L7.** No prompt versioning (`memory/prompts.py`)
- **L8.** `insight_items` types missing from public API `__all__` (`memory/__init__.py`)
- **L9.** Duplicate `_call_llm_with_json` in `memory_keeper.py` and `reflection.py`
- **L10.** Wrong docstring run commands in demos 02, 03, 04
- **L11.** Code duplication between demos 08 and 09
- **L12.** XSS via `unsafe_allow_html=True` with user content in demo 07

---

## Suggested Implementation Sequencing

| Phase | Focus | Items |
|-------|-------|-------|
| 1 (Critical fixes) | Correctness & safety | C1, C2, C3, H1, H2, H6 |
| 2 (Async correctness) | Stop blocking the event loop | C4, H3, H4 |
| 3 (Server hardening) | Production readiness | H7, H8, H5, H9, H10, M9 |
| 4 (Code quality) | Maintainability | M1–M13, all Low items |

---

## Implementation Feedback

- `C1` — `fixed`: SQLite native vector search now emits a single predicate chain and no longer generates two `WHERE` clauses in `memory/db/sqlite_backend.py`.
- `C2` — `fixed`: SQLite query and vector-search filter keys are now validated against per-container allowlists before SQL is built.
- `C3` — `fixed`: `AgentMemoryConfig` and `OrchestratorConfig` now share the same default embedding model and dimensions.
- `C4` — `fixed`: `memory/db/cosmos_backend.py` now uses the async Cosmos client and async query iteration for live Azure/Cosmos paths.
- `H1` — `fixed`: `AgentMemory.end_session()` no longer closes and discards the entire instance; it now only resets session state.
- `H2` — `partially fixed`: background tasks are now tracked, awaited on shutdown, and logged on failure, but the background-task architecture itself remains in place.
- `H3` — `fixed`: adapter sync wrappers no longer call `run_until_complete()` on the active loop and instead use a safe compatibility runner.
- `H4` — `fixed`: `AgentMemory.get_context()` is now async-only across the library/server/demos, so context retrieval no longer relies on a sync compatibility path.
- `H5` — `fixed`: Cosmos vector search now returns explicit per-container field sets that match the active code paths used by SQLite results.
- `H6` — `fixed`: Cosmos `get_by_id()` and `delete()` now swallow only not-found cases and propagate other failures.
- `H7` — `fixed`: server session removal and eviction now release the pool lock before slow `end_session()` / `close()` work.
- `H8` — `fixed`: `/search`, `/users/{user_id}/insights`, and `/users/{user_id}/sessions` now use ephemeral read-only memory instances instead of temporary full sessions.
- `H9` — `fixed`: SQLite `batch_upsert()` now runs inside a single transaction and updates vector indexes in the same batch.
- `H10` — `fixed`: SQLite vector index DELETE+INSERT operations now execute in the same transaction as the parent upsert/delete path.
- `M1` — `fixed`: active non-archived code paths were migrated off `datetime.utcnow()` to timezone-aware UTC timestamps.
- `M2` — `fixed`: restore now has explicit semantics; unsupported restore calls are rejected and active-session restore is implemented in the library/server flow.
- `M3` — `deferred`: the Pydantic storage models were not fully wired into all database upsert boundaries in this pass.
- `M4` — `fixed`: `MemoryKeeper` now imports the shared `SessionInitContext` model instead of maintaining a duplicate definition.
- `M5` — `partially fixed`: the embedding provider now validates empty input, chunks batches, and retries transient failures, but deployment-specific validation remains lightweight.
- `M6` — `fixed`: long-term profile synthesis now uses generic prompt templates instead of finance-specific prompt text.
- `M7` — `fixed`: SQLite row deserialization now parses `source_session_ids`.
- `M8` — `fixed`: Cosmos `close()` now awaits the owned async client shutdown instead of only nulling the reference.
- `M9` — `partially fixed`: the server now has a config-driven auth gate, but it is still scaffolding rather than a full production authorization model.
- `M10` — `fixed`: `agent/single_agent.py` now exposes a proper async `close()` path so the Agent Framework context manager can be exited cleanly.
- `M11` — `fixed`: import-time `load_dotenv()` side effects were removed from the Cosmos backend.
- `M12` — `fixed`: `/sessions/context` is now exposed as GET-only and both Python clients were updated to use query-parameter reads instead of POST.
- `M13` — `fixed`: backend result-shape drift was reduced by normalizing the Cosmos vector-search field sets to match active SQLite consumers.
- `L1` — `fixed`: base-agent chat history is now bounded before persisting back to the state store.
- `L2` — `fixed`: the typo in `agent/single_agent.py` was corrected from `hallunicate` to `hallucinate`.
- `L3` — `fixed`: private Agent Framework `_local_mcp_tools` access was removed from `agent/single_agent.py`.
- `L4` — `fixed`: the Python memory client now has bounded retries and explicit per-request timeouts through a shared request helper.
- `L5` — `fixed`: `MemoryServiceClient` now requires `async with` or an explicit `await open()` before use, so it can no longer silently create and leak an unmanaged HTTP client.
- `L6` — `fixed`: `server/main.py` now uses `ServerConfig` for the main server/runtime settings instead of reading most values ad hoc.
- `L7` — `fixed`: prompt version constants were added for the active prompt templates.
- `L8` — `fixed`: insight-item public types were exported from `memory/__init__.py`.
- `L9` — `fixed`: the duplicate `_call_llm_with_json` logic was consolidated into `memory/core/llm_json.py`.
- `L10` — `already resolved`: the demo run-command drift called out in the review had already been corrected during the earlier rc4 cleanup pass.
- `L11` — `deferred`: demo 08 and 09 still share substantial duplication and were not refactored in this implementation batch.
- `L12` — `fixed`: demo 07 now HTML-escapes rendered conversation content before using `unsafe_allow_html=True`.
