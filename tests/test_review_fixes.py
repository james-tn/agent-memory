import asyncio
import sqlite3

import pytest

from memory.core.agent_memory import AgentMemory
from memory.db.base import ContainerType
from memory.db.cosmos_backend import CosmosDBDatabase
from memory.db.sqlite_backend import SQLiteDatabase


class FakeEmbeddingProvider:
    def get_embedding(self, text):
        return [0.1, 0.2]

    def get_embeddings_batch(self, texts):
        return [[0.1, 0.2] for _ in texts]


class _FakeCursor:
    def fetchall(self):
        return []


def test_sqlite_vector_search_uses_single_where_clause(monkeypatch, tmp_path):
    db = SQLiteDatabase(db_path=str(tmp_path / "memory.db"), embedding_provider=FakeEmbeddingProvider())
    captured = {}

    class FakeConnection:
        def execute(self, query, params):
            captured["query"] = query
            captured["params"] = params
            return _FakeCursor()

    db._conn = FakeConnection()
    db._vec_available = True

    asyncio.run(
        db._vector_search_native(
            ContainerType.INTERACTIONS,
            [0.1, 0.2],
            "content_vector",
            3,
            {"user_id": "u1"},
        )
    )

    assert captured["query"].count("WHERE") == 1
    assert "WHERE t.user_id = ?\n            AND v.content_vector MATCH ?" in captured["query"]


def test_sqlite_query_rejects_invalid_filter_keys(tmp_path):
    db = SQLiteDatabase(db_path=str(tmp_path / "memory.db"), embedding_provider=FakeEmbeddingProvider())
    asyncio.run(db.initialize())

    with pytest.raises(ValueError):
        asyncio.run(db.query(ContainerType.INTERACTIONS, {"user_id; DROP TABLE interactions": "u1"}))


def test_sqlite_row_to_dict_parses_source_session_ids(tmp_path):
    db = SQLiteDatabase(db_path=str(tmp_path / "memory.db"), embedding_provider=FakeEmbeddingProvider())
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE test (id TEXT, source_session_ids TEXT)")
    conn.execute("INSERT INTO test VALUES (?, ?)", ("i1", '["s1","s2"]'))
    row = conn.execute("SELECT id, source_session_ids FROM test").fetchone()
    parsed = db._row_to_dict(row)
    assert parsed["source_session_ids"] == ["s1", "s2"]


def test_agent_memory_end_session_keeps_instance_reusable(monkeypatch, install_agent_framework_stubs):
    memory = AgentMemory(user_id="user-1", embedding_provider=FakeEmbeddingProvider(), session_id="session-1")
    memory._session_started = True

    class FakeOrchestrator:
        def __init__(self):
            self.called = False

        async def end_session(self, trigger_reflection=True):
            self.called = True
            return {"session_summary": "done"}

    orchestrator = FakeOrchestrator()
    memory._orchestrator = orchestrator
    result = asyncio.run(memory.end_session())

    assert result["session_summary"] == "done"
    assert memory._orchestrator is orchestrator


def test_agent_memory_close_does_not_close_shared_database(install_agent_framework_stubs):
    memory = AgentMemory(user_id="user-1", embedding_provider=FakeEmbeddingProvider(), database=object())

    class FakeOrchestrator:
        def __init__(self):
            self.close_calls = []

        async def close(self, *, close_database=None):
            self.close_calls.append(close_database)

    orchestrator = FakeOrchestrator()
    memory._orchestrator = orchestrator

    asyncio.run(memory.close())

    assert orchestrator.close_calls == [False]


def test_agent_memory_restore_requires_explicit_session_id(install_agent_framework_stubs):
    memory = AgentMemory(user_id="user-1", embedding_provider=FakeEmbeddingProvider())

    with pytest.raises(ValueError):
        asyncio.run(memory.start_session(restore=True))


def test_cosmos_close_awaits_owned_client():
    class FakeClient:
        def __init__(self):
            self.closed = False

        async def close(self):
            self.closed = True

    client = FakeClient()
    db = CosmosDBDatabase(cosmos_client=client, embedding_provider=FakeEmbeddingProvider())
    db._owns_client = True

    asyncio.run(db.close())

    assert client.closed is True


def test_cosmos_not_found_is_swallowed_but_other_errors_propagate():
    CosmosResourceNotFoundError = CosmosDBDatabase.get_by_id.__globals__["CosmosResourceNotFoundError"]

    class FakeContainer:
        async def read_item(self, item, partition_key):
            raise CosmosResourceNotFoundError(status_code=404, message="missing")

    db = CosmosDBDatabase(cosmos_client=object(), embedding_provider=FakeEmbeddingProvider())
    db._containers = {ContainerType.INTERACTIONS: FakeContainer()}

    result = asyncio.run(db.get_by_id(ContainerType.INTERACTIONS, "missing", "u1"))
    assert result is None

    class ExplodingContainer:
        async def read_item(self, item, partition_key):
            raise RuntimeError("boom")

    db._containers = {ContainerType.INTERACTIONS: ExplodingContainer()}

    with pytest.raises(RuntimeError):
        asyncio.run(db.get_by_id(ContainerType.INTERACTIONS, "missing", "u1"))
