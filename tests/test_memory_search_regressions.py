import asyncio
from types import SimpleNamespace

from memory.core.orchestrator import MemoryOrchestrator
from memory.db.base import SearchResult, ContainerType


class FakeEmbeddingProvider:
    def get_embedding(self, text):
        text_lower = text.lower()
        if "penicillin" in text_lower or "allergy" in text_lower:
            return [1.0, 0.0]
        if "seattle" in text_lower or "travel" in text_lower:
            return [0.8, 0.2]
        return [0.2, 0.1]

    def get_embeddings_batch(self, texts):
        return [self.get_embedding(text) for text in texts]


class RecordingDatabase:
    def __init__(self, interaction_results=None):
        self.calls = []
        self._interaction_results = interaction_results or {}

    async def vector_search(self, container, query_embedding, vector_field, top_k, filters):
        self.calls.append((container, vector_field, top_k, filters))
        if container == ContainerType.INTERACTIONS:
            return self._interaction_results.get(vector_field, [])
        return []


class FakeMemoryKeeper:
    def __init__(self, *, cumulative_summary="", turn_buffer=None):
        self.cumulative_summary = cumulative_summary
        self.turn_buffer = turn_buffer or []
        self.wait_calls = 0

    async def wait_for_pending_tasks(self):
        self.wait_calls += 1


def _build_orchestrator(database, memory_keeper):
    orchestrator = MemoryOrchestrator(
        user_id="user-1",
        database=database,
        embedding_provider=FakeEmbeddingProvider(),
    )
    orchestrator._memory_keeper = memory_keeper

    async def fake_initialize():
        orchestrator._initialized = True

    orchestrator.initialize = fake_initialize
    return orchestrator


def test_retrieve_facts_waits_for_pending_tasks_and_uses_interaction_summary_vectors():
    db = RecordingDatabase(
        interaction_results={
            "summary_vector": [
                SearchResult(
                    id="interaction-1",
                    document={
                        "summary": "Riley has a penicillin allergy and often travels between Seattle and New York.",
                        "content": "user: Riley mentioned a penicillin allergy.",
                    },
                    score=0.95,
                )
            ]
        }
    )
    memory_keeper = FakeMemoryKeeper()
    orchestrator = _build_orchestrator(db, memory_keeper)

    result = asyncio.run(
        orchestrator.retrieve_facts(
            "What allergy should we remember about Riley?",
            top_k=3,
            include_summaries=False,
            include_insights=False,
        )
    )

    assert memory_keeper.wait_calls == 1
    assert db.calls[0] == (
        ContainerType.INTERACTIONS,
        "summary_vector",
        3,
        {"user_id": "user-1", "agent_id": "default"},
    )
    assert "penicillin allergy" in result


def test_retrieve_facts_falls_back_to_active_session_memory_when_not_yet_persisted():
    db = RecordingDatabase()
    memory_keeper = FakeMemoryKeeper(
        cumulative_summary="Riley has a penicillin allergy and prefers concise answers.",
        turn_buffer=[
            SimpleNamespace(role="user", content="I'm allergic to penicillin."),
            SimpleNamespace(role="assistant", content="I'll remember your penicillin allergy."),
        ],
    )
    orchestrator = _build_orchestrator(db, memory_keeper)

    result = asyncio.run(
        orchestrator.retrieve_facts(
            "What allergy should we remember about Riley?",
            top_k=3,
            include_summaries=False,
            include_insights=False,
        )
    )

    assert "[Current Session Summary]" in result
    assert "penicillin" in result.lower()
