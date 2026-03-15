import asyncio
import importlib
import sys
import types

from memory.db.base import ContainerType
from memory.db.factory import DatabaseType, create_database


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None


class FakeConnection:
    def __init__(self):
        self.executed = []
        self.rows = []
        self.row = None

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        if sql.startswith("DELETE"):
            return "DELETE 1"
        return "OK"

    async def fetch(self, sql, *args):
        self.executed.append((sql, args))
        return self.rows

    async def fetchrow(self, sql, *args):
        self.executed.append((sql, args))
        return self.row

    def transaction(self):
        return FakeTransaction()


class FakeAcquire:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, exc_type, exc, tb):
        return None


class FakePool:
    def __init__(self):
        self.conn = FakeConnection()
        self.closed = False

    def acquire(self):
        return FakeAcquire(self.conn)

    async def fetch(self, sql, *args):
        return await self.conn.fetch(sql, *args)

    async def fetchrow(self, sql, *args):
        return await self.conn.fetchrow(sql, *args)

    async def execute(self, sql, *args):
        return await self.conn.execute(sql, *args)

    async def close(self):
        self.closed = True


def _install_asyncpg_stub():
    module = types.ModuleType("asyncpg")
    module.Pool = FakePool

    async def create_pool(*args, **kwargs):
        return FakePool()

    module.create_pool = create_pool
    sys.modules["asyncpg"] = module


def test_postgresql_backend_initializes_and_creates_tables(monkeypatch):
    _install_asyncpg_stub()
    backend_module = importlib.import_module("memory.db.postgresql_backend")
    PostgreSQLDatabase = backend_module.PostgreSQLDatabase

    pool = FakePool()
    backend = PostgreSQLDatabase(pool=pool, vector_dimensions=4)

    asyncio.run(backend.initialize())

    assert any("CREATE EXTENSION IF NOT EXISTS vector" in sql for sql, _ in pool.conn.executed)
    assert any("CREATE TABLE IF NOT EXISTS interactions" in sql for sql, _ in pool.conn.executed)
    assert backend.get_capabilities().supports_transactions is True


def test_postgresql_backend_upsert_and_vector_search(monkeypatch):
    _install_asyncpg_stub()
    backend_module = importlib.import_module("memory.db.postgresql_backend")
    PostgreSQLDatabase = backend_module.PostgreSQLDatabase

    pool = FakePool()
    backend = PostgreSQLDatabase(pool=pool, vector_dimensions=4)

    doc = {
        "id": "interaction-1",
        "user_id": "user-1",
        "agent_id": "agent-a",
        "session_id": "session-1",
        "timestamp": "2026-03-14T00:00:00+00:00",
        "content": "hello",
        "summary": "summary",
        "metadata": {"topic": "greeting"},
        "content_vector": [0.1, 0.2, 0.3, 0.4],
        "summary_vector": [0.5, 0.6, 0.7, 0.8],
        "created_at": "2026-03-14T00:00:00+00:00",
        "updated_at": "2026-03-14T00:00:00+00:00",
    }

    asyncio.run(backend.upsert(ContainerType.INTERACTIONS, doc))
    upsert_sql, upsert_args = pool.conn.executed[-1]
    assert "::vector" in upsert_sql
    assert "::jsonb" in upsert_sql
    assert "[0.1,0.2,0.3,0.4]" in upsert_args

    pool.conn.rows = [
        {
            "id": "interaction-1",
            "user_id": "user-1",
            "agent_id": "agent-a",
            "session_id": "session-1",
            "timestamp": "2026-03-14T00:00:00+00:00",
            "content": "hello",
            "summary": "summary",
            "metadata": '{"topic":"greeting"}',
            "content_vector": "[0.1,0.2,0.3,0.4]",
            "summary_vector": "[0.5,0.6,0.7,0.8]",
            "created_at": "2026-03-14T00:00:00+00:00",
            "updated_at": "2026-03-14T00:00:00+00:00",
            "similarity_score": 0.91,
        }
    ]
    results = asyncio.run(
        backend.vector_search(
            ContainerType.INTERACTIONS,
            query_embedding=[0.1, 0.2, 0.3, 0.4],
            vector_field="summary_vector",
            top_k=3,
            filters={"user_id": "user-1", "agent_id": "agent-a"},
        )
    )

    assert results[0].score == 0.91
    assert results[0].document["metadata"] == {"topic": "greeting"}
    search_sql, search_args = pool.conn.executed[-1]
    assert "summary_vector <=> $1::vector" in search_sql
    assert search_args[0] == "[0.1,0.2,0.3,0.4]"


def test_postgresql_backend_hybrid_search_and_filter_validation(monkeypatch):
    _install_asyncpg_stub()
    backend_module = importlib.import_module("memory.db.postgresql_backend")
    PostgreSQLDatabase = backend_module.PostgreSQLDatabase

    pool = FakePool()
    backend = PostgreSQLDatabase(pool=pool, vector_dimensions=4)
    pool.conn.rows = [
        {
            "id": "insight-1",
            "user_id": "user-1",
            "agent_id": "agent-a",
            "session_ids": '["session-1"]',
            "insight_type": "session",
            "insight_text": "Prefers Rust",
            "insight_vector": "[0.9,0.1,0.2,0.3]",
            "confidence": 0.9,
            "importance": "high",
            "category": "preferences",
            "reflection_flag": "insight",
            "processed": False,
            "source_insight_ids": "[]",
            "source_session_ids": '["session-1"]',
            "date_added": "2026-03-14T00:00:00+00:00",
            "last_accessed": "2026-03-14T00:00:00+00:00",
            "access_count": 1,
            "is_deleted": False,
            "deleted_at": None,
            "mutation_history": '[{"event":"ADD"}]',
            "created_at": "2026-03-14T00:00:00+00:00",
            "updated_at": "2026-03-14T00:00:00+00:00",
            "hybrid_score": 0.88,
        }
    ]

    results = asyncio.run(
        backend.hybrid_search(
            ContainerType.INSIGHTS,
            query_text="rust",
            query_embedding=[0.9, 0.1, 0.2, 0.3],
            vector_field="insight_vector",
            top_k=2,
            filters={"user_id": "user-1", "agent_id": "agent-a"},
        )
    )
    assert results[0].score_type == "hybrid"
    assert results[0].document["mutation_history"] == [{"event": "ADD"}]
    assert "plainto_tsquery" in pool.conn.executed[-1][0]

    try:
        asyncio.run(
            backend.query(
                ContainerType.INSIGHTS,
                filters={"bogus": "value"},
            )
        )
    except ValueError as exc:
        assert "Unsupported filter keys" in str(exc)
    else:
        raise AssertionError("Expected invalid filter keys to be rejected")


def test_factory_creates_postgresql_backend(monkeypatch):
    _install_asyncpg_stub()
    backend = create_database(
        db_type=DatabaseType.POSTGRESQL,
        pool=FakePool(),
        vector_dimensions=8,
    )

    assert backend.get_capabilities().backend_name == "postgresql"
