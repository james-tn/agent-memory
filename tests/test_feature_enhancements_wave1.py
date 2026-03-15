import asyncio

from memory.core.reflection import (
    ComprehensiveSessionAnalysis,
    ConflictResolutionResult,
    ConflictResolutionAction,
    Reflection,
    ReflectionConfig,
)
from memory.db.base import SearchResult


class FakeEmbeddingProvider:
    def get_embedding(self, text):
        return [float(len(text))]

    def get_embeddings_batch(self, texts):
        return [[float(len(text))] for text in texts]


class FakeDatabase:
    def __init__(self, docs=None):
        self.docs = docs or {}

    async def upsert(self, container, document, partition_key=None):
        self.docs[document["id"]] = dict(document)
        return self.docs[document["id"]]

    async def get_by_id(self, container, document_id, partition_key=None):
        return self.docs.get(document_id)

    async def query(self, container, filters, order_by=None, limit=None):
        results = []
        for doc in self.docs.values():
            if all(doc.get(key) == value for key, value in filters.items()):
                results.append(dict(doc))
        return results[:limit] if limit is not None else results

    async def vector_search(self, container, query_embedding, vector_field="insight_vector", top_k=5, filters=None):
        results = []
        for doc in self.docs.values():
            if filters and any(doc.get(key) != value for key, value in filters.items()):
                continue
            results.append(SearchResult(id=doc["id"], document=dict(doc), score=0.9))
        return results[:top_k]


def test_reconcile_updates_existing_insight():
    existing = {
        "id": "ins-1",
        "user_id": "u1",
        "agent_id": "agent-a",
        "session_ids": ["s0"],
        "insight_type": "session",
        "insight_text": "Prefers Python",
        "category": "preferences",
        "confidence": 0.8,
        "importance": "medium",
        "processed": False,
        "is_deleted": False,
        "mutation_history": [],
        "created_at": "2026-03-14T00:00:00+00:00",
        "updated_at": "2026-03-14T00:00:00+00:00",
    }
    reflection = Reflection(
        agent_id="agent-a",
        database=FakeDatabase({"ins-1": existing}),
        embedding_provider=FakeEmbeddingProvider(),
        chat_client=object(),
        config=ReflectionConfig(),
    )

    reflection._call_llm_with_json = lambda **kwargs: ConflictResolutionResult(
        memory=[
            ConflictResolutionAction(
                id="0",
                text="Prefers Rust now",
                event="UPDATE",
                category="preferences",
                confidence=0.95,
                importance="high",
                rationale="Latest preference supersedes the older one.",
            )
        ]
    )

    stored_docs, mutations = asyncio.run(
        reflection.reconcile_session_insights(
            user_id="u1",
            session_id="s1",
            extracted_insights=[
                {
                    "insight_text": "Prefers Rust now",
                    "category": "preferences",
                    "confidence": 0.95,
                    "importance": "high",
                }
            ],
        )
    )

    assert len(stored_docs) == 1
    assert stored_docs[0]["id"] == "ins-1"
    assert stored_docs[0]["insight_text"] == "Prefers Rust now"
    assert stored_docs[0]["session_ids"] == ["s0", "s1"]
    assert stored_docs[0]["mutation_history"][-1]["event"] == "UPDATE"
    assert len(mutations) == 1


def test_reconcile_soft_deletes_and_adds():
    existing = {
        "id": "ins-1",
        "user_id": "u1",
        "agent_id": "agent-a",
        "session_ids": ["s0"],
        "insight_type": "session",
        "insight_text": "Likes pizza",
        "category": "preferences",
        "confidence": 0.8,
        "importance": "medium",
        "processed": False,
        "is_deleted": False,
        "mutation_history": [],
        "created_at": "2026-03-14T00:00:00+00:00",
        "updated_at": "2026-03-14T00:00:00+00:00",
    }
    database = FakeDatabase({"ins-1": existing})
    reflection = Reflection(
        agent_id="agent-a",
        database=database,
        embedding_provider=FakeEmbeddingProvider(),
        chat_client=object(),
        config=ReflectionConfig(),
    )

    reflection._call_llm_with_json = lambda **kwargs: ConflictResolutionResult(
        memory=[
            ConflictResolutionAction(
                id="0",
                event="DELETE",
                rationale="The new statement contradicts the previous preference.",
            ),
            ConflictResolutionAction(
                event="ADD",
                text="Dislikes pizza",
                category="preferences",
                confidence=0.9,
                importance="high",
                rationale="Store the new preference separately.",
            ),
        ]
    )

    stored_docs, mutations = asyncio.run(
        reflection.reconcile_session_insights(
            user_id="u1",
            session_id="s1",
            extracted_insights=[
                {
                    "insight_text": "Dislikes pizza",
                    "category": "preferences",
                    "confidence": 0.9,
                    "importance": "high",
                }
            ],
        )
    )

    assert database.docs["ins-1"]["is_deleted"] is True
    assert database.docs["ins-1"]["mutation_history"][-1]["event"] == "DELETE"
    assert len(stored_docs) == 1
    assert stored_docs[0]["insight_text"] == "Dislikes pizza"
    assert stored_docs[0]["mutation_history"][-1]["event"] == "ADD"
    assert len(mutations) == 2


def test_custom_extraction_prompt_uses_configured_categories():
    captured = {}
    reflection = Reflection(
        agent_id="agent-a",
        database=FakeDatabase(),
        embedding_provider=FakeEmbeddingProvider(),
        chat_client=object(),
        config=ReflectionConfig(
            insight_categories=["technology", "career"],
            custom_extraction_prompt="CATEGORIES:\n{category_instructions}\nCONTENT:\n{session_content}",
        ),
    )

    def fake_call(*, system_prompt, user_prompt, output_model):
        captured["user_prompt"] = user_prompt
        return ComprehensiveSessionAnalysis(
            session_summary="summary",
            key_topics=["topic"],
            insights=[],
            has_meaningful_insights=False,
        )

    reflection._call_llm_with_json = fake_call

    result = asyncio.run(reflection._generate_comprehensive_analysis("user: hi"))

    assert result.session_summary == "summary"
    assert "technology" in captured["user_prompt"]
    assert "career" in captured["user_prompt"]
    assert "user: hi" in captured["user_prompt"]
