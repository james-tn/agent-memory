import asyncio

from azure.core.exceptions import ResourceNotFoundError

from memory.db.azure_search_backend import AzureAISearchDatabase
from memory.db.base import ContainerType
from memory.db.factory import DatabaseType, create_database


class AsyncPager:
    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        async def iterator():
            for item in self._items:
                yield item

        return iterator()


class FakeSearchClient:
    def __init__(self):
        self.documents = {}
        self.search_results = []
        self.last_search_kwargs = None
        self.closed = False

    async def merge_or_upload_documents(self, documents, **kwargs):
        for document in documents:
            self.documents[document["id"]] = document
        return [type("Result", (), {"succeeded": True})()]

    async def get_document(self, key, selected_fields=None, **kwargs):
        if key not in self.documents:
            raise ResourceNotFoundError("missing")
        return self.documents[key]

    async def delete_documents(self, documents, **kwargs):
        for document in documents:
            self.documents.pop(document["id"], None)
        return [type("Result", (), {"succeeded": True})()]

    async def search(self, **kwargs):
        self.last_search_kwargs = kwargs
        return AsyncPager(self.search_results)

    async def close(self):
        self.closed = True


class FakeIndexClient:
    def __init__(self):
        self.indexes = []
        self.closed = False

    async def create_or_update_index(self, index, **kwargs):
        self.indexes.append(index)
        return index

    async def close(self):
        self.closed = True


def _backend():
    search_clients = {
        ContainerType.INTERACTIONS: FakeSearchClient(),
        ContainerType.INSIGHTS: FakeSearchClient(),
        ContainerType.SESSION_SUMMARIES: FakeSearchClient(),
    }
    return AzureAISearchDatabase(
        index_client=FakeIndexClient(),
        search_clients=search_clients,
        vector_dimensions=4,
    )


def test_azure_search_backend_initializes_indexes():
    backend = _backend()

    asyncio.run(backend.initialize())
    asyncio.run(backend.initialize())

    assert len(backend._index_client.indexes) == 3
    assert sorted(index.name for index in backend._index_client.indexes) == [
        "agent-memory-insights",
        "agent-memory-interactions",
        "agent-memory-session-summaries",
    ]


def test_azure_search_backend_vector_and_hybrid_search_decode_fields():
    backend = _backend()
    asyncio.run(backend.initialize())

    insights_client = backend._search_clients[ContainerType.INSIGHTS]
    asyncio.run(
        backend.upsert(
            ContainerType.INSIGHTS,
            {
                "id": "insight-1",
                "user_id": "user-1",
                "agent_id": "agent-a",
                "session_ids": ["session-1"],
                "insight_type": "session",
                "insight_text": "Prefers Rust",
                "insight_vector": [0.1, 0.2, 0.3, 0.4],
                "category": "preferences",
                "confidence": 0.9,
                "importance": "high",
                "processed": False,
                "source_insight_ids": [],
                "source_session_ids": ["session-1"],
                "date_added": "2026-03-14T00:00:00+00:00",
                "last_accessed": "2026-03-14T00:00:00+00:00",
                "access_count": 1,
                "is_deleted": False,
                "deleted_at": None,
                "mutation_history": [{"event": "ADD"}],
                "created_at": "2026-03-14T00:00:00+00:00",
                "updated_at": "2026-03-14T00:00:00+00:00",
            },
        )
    )
    insights_client.search_results = [
        {
            **insights_client.documents["insight-1"],
            "@search.score": 2.75,
        }
    ]

    vector_results = asyncio.run(
        backend.vector_search(
            ContainerType.INSIGHTS,
            query_embedding=[0.9, 0.1, 0.2, 0.3],
            vector_field="insight_vector",
            top_k=3,
            filters={"user_id": "user-1", "agent_id": "agent-a"},
        )
    )
    hybrid_results = asyncio.run(
        backend.hybrid_search(
            ContainerType.INSIGHTS,
            query_text="rust",
            query_embedding=[0.9, 0.1, 0.2, 0.3],
            vector_field="insight_vector",
            top_k=3,
            filters={"user_id": "user-1", "agent_id": "agent-a"},
        )
    )

    assert vector_results[0].document["mutation_history"] == [{"event": "ADD"}]
    assert vector_results[0].document["session_ids"] == ["session-1"]
    assert vector_results[0].score_type == "similarity"
    assert hybrid_results[0].score_type == "hybrid"
    assert "user_id eq 'user-1'" in insights_client.last_search_kwargs["filter"]
    assert "agent_id eq 'agent-a'" in insights_client.last_search_kwargs["filter"]
    assert insights_client.last_search_kwargs["vector_queries"][0].fields == "insight_vector"
    assert insights_client.last_search_kwargs["search_text"] == "rust"


def test_azure_search_backend_rejects_unknown_filter_keys():
    backend = _backend()
    asyncio.run(backend.initialize())

    try:
        asyncio.run(
            backend.query(
                ContainerType.INTERACTIONS,
                filters={"bogus": "value"},
            )
        )
    except ValueError as exc:
        assert "Unsupported filter keys" in str(exc)
    else:
        raise AssertionError("Expected invalid filter keys to be rejected")


def test_factory_creates_azure_ai_search_backend():
    search_clients = {
        ContainerType.INTERACTIONS: FakeSearchClient(),
        ContainerType.INSIGHTS: FakeSearchClient(),
        ContainerType.SESSION_SUMMARIES: FakeSearchClient(),
    }
    backend = create_database(
        db_type=DatabaseType.AZURE_AI_SEARCH,
        index_client=FakeIndexClient(),
        search_clients=search_clients,
        vector_dimensions=8,
    )

    assert backend.__class__.__name__ == "AzureAISearchDatabase"
    assert backend.get_capabilities().backend_name == "azure_ai_search"
