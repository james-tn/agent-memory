import asyncio
import importlib
from types import SimpleNamespace


class FakeEmbeddingProvider:
    def get_embedding(self, text):
        return [0.1, 0.2]

    def get_embeddings_batch(self, texts):
        return [[0.1, 0.2] for _ in texts]


class FakeContext:
    def __init__(self, user_text="hello", assistant_text="world"):
        self.input_messages = [SimpleNamespace(role="user", text=user_text)]
        self.response = SimpleNamespace(messages=[SimpleNamespace(text=assistant_text)])
        self.instructions = []

    def extend_instructions(self, source_id, text):
        self.instructions.append((source_id, text))


def test_before_run_injects_memory_and_recalled_facts(monkeypatch, install_agent_framework_stubs):
    module = importlib.import_module("memory.core.agent_memory")
    AgentMemory = module.AgentMemory
    AgentMemoryConfig = module.AgentMemoryConfig

    memory = AgentMemory(
        user_id="user-1",
        embedding_provider=FakeEmbeddingProvider(),
        config=AgentMemoryConfig(auto_enrich_context=True),
    )

    async def fake_ensure():
        return None

    async def fake_start_session(*args, **kwargs):
        memory._session_started = True
        return {"session_id": "session-1"}

    async def fake_search(*args, **kwargs):
        return "remembered facts"

    async def fake_get_context_async():
        return "memory context"

    monkeypatch.setattr(memory, "_ensure_initialized", fake_ensure)
    monkeypatch.setattr(memory, "start_session", fake_start_session)
    monkeypatch.setattr(memory, "get_context", fake_get_context_async)
    monkeypatch.setattr(memory, "search", fake_search)
    monkeypatch.setattr(memory, "_should_enrich", lambda text: True)

    context = FakeContext(user_text="what did we discuss?")
    asyncio.run(memory.before_run(agent=None, session=None, context=context, state={}))

    assert context.instructions == [
        ("agent_memory", "memory context\n\n### Relevant Memory\nremembered facts")
    ]


def test_post_run_hooks_store_turns(monkeypatch, install_agent_framework_stubs):
    module = importlib.import_module("memory.core.agent_memory")
    AgentMemory = module.AgentMemory

    memory = AgentMemory(user_id="user-1", embedding_provider=FakeEmbeddingProvider())
    memory._session_started = True

    recorded = {}

    async def fake_add_turn(user_text, assistant_text, metadata=None):
        recorded["user"] = user_text
        recorded["assistant"] = assistant_text

    monkeypatch.setattr(memory, "add_turn", fake_add_turn)

    context = FakeContext(user_text="hi", assistant_text="hello")
    asyncio.run(memory.after_run(agent=None, session=None, context=context, state={}))

    assert recorded == {"user": "hi", "assistant": "hello"}


def test_only_current_agent_framework_hooks_are_exposed(install_agent_framework_stubs):
    module = importlib.import_module("memory.core.agent_memory")
    AgentMemory = module.AgentMemory

    memory = AgentMemory(user_id="user-1", embedding_provider=FakeEmbeddingProvider())

    assert hasattr(memory, "before_run")
    assert hasattr(memory, "after_run")
    assert not hasattr(memory, "invoking")
    assert not hasattr(memory, "invoked")


def test_search_forwards_search_flags(monkeypatch, install_agent_framework_stubs):
    module = importlib.import_module("memory.core.agent_memory")
    AgentMemory = module.AgentMemory

    memory = AgentMemory(user_id="user-1", embedding_provider=FakeEmbeddingProvider())
    called = {}

    class FakeOrchestrator:
        async def retrieve_facts(self, query, **kwargs):
            called["query"] = query
            called.update(kwargs)
            return "ok"

    async def fake_ensure():
        memory._orchestrator = FakeOrchestrator()
        memory._initialized = True

    monkeypatch.setattr(memory, "_ensure_initialized", fake_ensure)

    result = asyncio.run(
        memory.search(
            "risk tolerance",
            top_k=2,
            search_interactions=False,
            search_insights=True,
            search_summaries=True,
        )
    )

    assert result == "ok"
    assert called == {
        "query": "risk tolerance",
        "top_k": 2,
        "include_interactions": False,
        "include_summaries": True,
        "include_insights": True,
    }


def test_end_session_resets_session_state(install_agent_framework_stubs):
    module = importlib.import_module("memory.core.agent_memory")
    AgentMemory = module.AgentMemory

    memory = AgentMemory(user_id="user-1", embedding_provider=FakeEmbeddingProvider(), session_id="session-1")
    memory._session_started = True

    class FakeOrchestrator:
        async def end_session(self, trigger_reflection=True):
            return {"session_id": "session-1", "session_summary": "done"}

    memory._orchestrator = FakeOrchestrator()

    result = asyncio.run(memory.end_session())

    assert result["session_summary"] == "done"
    assert memory.session_id is None
    assert memory._session_started is False
