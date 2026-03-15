import asyncio
import importlib

import pytest

from memory.db.base import ContainerType, DatabaseCapabilities, SearchResult
from memory.db.factory import DatabaseType


class FakeEmbeddingProvider:
    def get_embedding(self, text):
        return [0.1, 0.2]

    def get_embeddings_batch(self, texts):
        return [[0.1, 0.2] for _ in texts]


class HybridCapableDatabase:
    def __init__(self, supports_hybrid=True):
        self.supports_hybrid = supports_hybrid
        self.calls = []

    async def initialize(self):
        return None

    async def close(self):
        return None

    def get_capabilities(self):
        return DatabaseCapabilities(
            supports_vector_search=True,
            supports_hybrid_search=self.supports_hybrid,
            supports_full_text_search=self.supports_hybrid,
        )

    async def vector_search(self, container, query_embedding, vector_field="content_vector", top_k=5, filters=None):
        self.calls.append(("vector", container, vector_field, filters))
        return [SearchResult(id="v1", document={"summary": "vector", "insight_text": "vector", "category": "general"}, score=0.5)]

    async def hybrid_search(self, container, query_text, query_embedding, vector_field="content_vector", text_fields=None, top_k=5, filters=None):
        self.calls.append(("hybrid", container, vector_field, filters))
        return [SearchResult(id="h1", document={"summary": "hybrid", "insight_text": "hybrid", "category": "general"}, score=0.9, score_type="hybrid")]

    async def upsert(self, container, document, partition_key=None):
        return document

    async def batch_upsert(self, container, documents, partition_key=None):
        return documents

    async def get_by_id(self, container, document_id, partition_key=None):
        return None

    async def delete(self, container, document_id, partition_key=None):
        return False

    async def query(self, container, filters, order_by=None, limit=None):
        return []


def test_fact_retrieval_auto_uses_hybrid_when_supported(install_agent_framework_stubs):
    module = importlib.import_module("memory.core.fact_retrieval")
    FactRetrieval = module.FactRetrieval
    FactRetrievalConfig = module.FactRetrievalConfig
    database = HybridCapableDatabase(supports_hybrid=True)
    retrieval = FactRetrieval(
        user_id="u1",
        database=database,
        embedding_provider=FakeEmbeddingProvider(),
        config=FactRetrievalConfig(search_mode="auto"),
    )

    asyncio.run(retrieval._search_insights("bedtime", 3))

    assert database.calls[0][0] == "hybrid"
    assert database.calls[0][1].value == ContainerType.INSIGHTS.value
    assert database.calls[0][3]["agent_id"] == "default"


def test_orchestrator_auto_falls_back_to_vector_when_hybrid_unsupported():
    module = importlib.import_module("memory.core.orchestrator")
    MemoryOrchestrator = module.MemoryOrchestrator
    OrchestratorConfig = module.OrchestratorConfig
    database = HybridCapableDatabase(supports_hybrid=False)
    orchestrator = MemoryOrchestrator(
        user_id="u1",
        database=database,
        db_type=DatabaseType.SQLITE,
        embedding_provider=FakeEmbeddingProvider(),
        openai_client=object(),
        chat_client=None,
        config=OrchestratorConfig(),
    )

    result = asyncio.run(
        orchestrator.retrieve_facts(
            "bedtime reading",
            top_k=2,
            include_interactions=True,
            include_summaries=False,
            include_insights=False,
            search_mode="auto",
        )
    )

    assert "[Conversation] vector" in result
    assert database.calls[0][0] == "vector"
    assert database.calls[0][3]["agent_id"] == "default"


def test_fact_retrieval_search_paths_do_not_require_azure_openai_env(monkeypatch, install_agent_framework_stubs):
    monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_VERSION", raising=False)

    module = importlib.import_module("memory.core.fact_retrieval")
    FactRetrieval = module.FactRetrieval
    FactRetrievalConfig = module.FactRetrievalConfig
    database = HybridCapableDatabase(supports_hybrid=True)
    retrieval = FactRetrieval(
        user_id="u1",
        database=database,
        embedding_provider=FakeEmbeddingProvider(),
        config=FactRetrievalConfig(search_mode="auto"),
    )

    results = asyncio.run(retrieval._search_interactions("bedtime", 2))
    assert results

    with pytest.raises(ValueError):
        retrieval._get_agent()
