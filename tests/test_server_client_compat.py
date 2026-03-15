import asyncio
import importlib

import httpx


def test_server_endpoints_map_current_memory_shapes(install_agent_framework_stubs):
    server_main = importlib.import_module("server.main")

    class FakeMemory:
        def __init__(self):
            self.session_id = "session-1"
            self.agent_id = "agent-a"
            self.config = type(
                "Config",
                (),
                {"include_longterm_insights": True, "num_recent_sessions_for_init": 5},
            )()
            self._orchestrator = type("Orchestrator", (), {"turn_count": 3})()

        async def get_context(self):
            return "ctx"

        async def add_turn(self, **kwargs):
            return {"turn_count": 3, "pruning_triggered": True}

        async def end_session(self, trigger_reflection=True):
            return {
                "session_summary": "summary",
                "insights_extracted": [{"id": "1"}],
                "synthesis_triggered": True,
            }

        async def close(self):
            return None

    class FakePool:
        def __init__(self):
            self.memory = FakeMemory()
            self.active_count = 1
            self.pooled_calls = 0
            self.search_calls = 0
            self.insight_calls = 0
            self.session_calls = 0

        async def get_or_create(self, **kwargs):
            self.pooled_calls += 1
            self.last_get_or_create = kwargs
            return self.memory

        async def get(self, user_id, agent_id, session_id):
            self.last_get = (user_id, agent_id, session_id)
            return self.memory

        async def search_memory(self, **kwargs):
            self.search_calls += 1
            self.last_search = kwargs
            return "results"

        async def list_insights(self, user_id, agent_id, limit=10):
            self.insight_calls += 1
            self.last_insights = (user_id, agent_id, limit)
            return [{"insight_text": "i1"}]

        async def list_sessions(self, user_id, agent_id, limit=10):
            self.session_calls += 1
            self.last_sessions = (user_id, agent_id, limit)
            return [{"summary": "s1"}]

        async def remove(self, user_id, agent_id, session_id):
            self.last_remove = (user_id, agent_id, session_id)
            return True

    server_main.session_pool = FakePool()
    server_main.start_time = server_main._utcnow()

    start = asyncio.run(server_main.start_session(server_main.StartSessionRequest(user_id="u1", agent_id="agent-a")))
    assert start.context == "ctx"
    assert start.insights_loaded is True
    assert start.recent_sessions_count == 5
    assert start.agent_id == "agent-a"
    assert server_main.session_pool.last_get_or_create["agent_id"] == "agent-a"

    stored = asyncio.run(
        server_main.store_turn(
            server_main.StoreTurnRequest(
                user_id="u1",
                agent_id="agent-a",
                session_id="session-1",
                user_message="hello",
                assistant_message="world",
            )
        )
    )
    assert stored.turn_count == 3
    assert stored.pruning_triggered is True

    ended = asyncio.run(
        server_main.end_session(
            server_main.EndSessionRequest(user_id="u1", agent_id="agent-a", session_id="session-1"),
            background_tasks=server_main.BackgroundTasks(),
        )
    )
    assert ended.summary == "summary"
    assert ended.insights_count == 1
    assert ended.synthesis_triggered is True

    searched = asyncio.run(server_main.search_memory(server_main.SearchRequest(user_id="u1", agent_id="agent-a", query="risk")))
    assert searched.results == "results"
    assert server_main.session_pool.last_search["search_mode"] == "auto"

    insights = asyncio.run(server_main.get_user_insights("u1", agent_id="agent-a"))
    sessions = asyncio.run(server_main.get_user_sessions("u1", agent_id="agent-a"))
    assert insights["insights"] == [{"insight_text": "i1"}]
    assert sessions["sessions"] == [{"summary": "s1"}]
    assert server_main.session_pool.search_calls == 1
    assert server_main.session_pool.insight_calls == 1
    assert server_main.session_pool.session_calls == 1


def test_server_read_only_pool_methods_use_shared_backend_without_ephemeral_memory(install_agent_framework_stubs):
    server_main = importlib.import_module("server.main")
    ContainerType = importlib.import_module("memory.db.base").ContainerType
    DatabaseType = importlib.import_module("memory.db.factory").DatabaseType

    class FakeDatabase:
        def __init__(self):
            self.query_calls = []
            self.initialize_calls = 0

        async def initialize(self):
            self.initialize_calls += 1

        async def query(self, container, filters, order_by=None, limit=None):
            self.query_calls.append((container, filters, order_by, limit))
            if container == ContainerType.INSIGHTS:
                return [{"id": "i1", "is_deleted": False}]
            return [{"id": "s1", "status": "completed"}]

        async def close(self):
            return None

    class FakeOrchestrator:
        instances = []

        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs
            self.close_calls = []
            FakeOrchestrator.instances.append(self)

        async def retrieve_facts(self, *args, **kwargs):
            self.retrieve_kwargs = kwargs
            return "shared-results"

        async def close(self, *, close_database=None):
            self.close_calls.append(close_database)

    fake_database = FakeDatabase()
    pool = server_main.SessionPool(openai_client=object(), db_type=DatabaseType.SQLITE)
    pool._shared_database = fake_database

    original_orchestrator = server_main.MemoryOrchestrator
    server_main.MemoryOrchestrator = FakeOrchestrator
    try:
        search_results = asyncio.run(
            pool.search_memory(
                user_id="u1",
                agent_id="agent-a",
                query="risk",
                top_k=4,
                search_interactions=True,
                search_insights=True,
                search_summaries=False,
                search_mode="hybrid",
            )
        )
        insights = asyncio.run(pool.list_insights("u1", "agent-a", limit=5))
        sessions = asyncio.run(pool.list_sessions("u1", "agent-a", limit=5))
    finally:
        server_main.MemoryOrchestrator = original_orchestrator

    assert search_results == "shared-results"
    assert insights == [{"id": "i1", "is_deleted": False}]
    assert sessions == [{"id": "s1", "status": "completed"}]
    assert fake_database.initialize_calls == 0
    assert fake_database.query_calls == [
        (ContainerType.INSIGHTS, {"user_id": "u1", "agent_id": "agent-a"}, None, 5),
        (ContainerType.SESSION_SUMMARIES, {"user_id": "u1", "agent_id": "agent-a", "status": "completed"}, "-end_time", 5),
    ]
    assert len(FakeOrchestrator.instances) == 1
    assert FakeOrchestrator.instances[0].retrieve_kwargs["search_mode"] == "hybrid"
    assert FakeOrchestrator.instances[0].close_calls == [False]


def test_server_exposes_get_only_context_route(install_agent_framework_stubs):
    server_main = importlib.import_module("server.main")

    assert hasattr(server_main, "get_context")
    assert not hasattr(server_main, "get_context_get")


def test_memory_service_client_parses_wire_shapes():
    client_module = importlib.import_module("client.memory_client")
    MemoryServiceClient = client_module.MemoryServiceClient

    responses = {
        ("POST", "/sessions/start"): {"session_id": "s1", "user_id": "u1", "agent_id": "agent-a", "context": "ctx", "insights_loaded": True, "recent_sessions_count": 2},
        ("GET", "/sessions/context"): {"context": "ctx2", "turn_count": 4},
        ("POST", "/sessions/turn"): {"success": True, "turn_count": 5, "pruning_triggered": True},
        ("POST", "/sessions/end"): {"success": True, "summary": "done", "insights_count": 2, "synthesis_triggered": True},
        ("POST", "/search"): {"results": "found", "query": "risk"},
        ("GET", "/users/u1/insights"): {"insights": [{"id": "i1"}]},
        ("GET", "/users/u1/sessions"): {"sessions": [{"id": "s1"}]},
    }

    def handler(request):
        if request.method == "POST" and request.url.path == "/sessions/start":
            payload = request.read().decode()
            assert '"agent_id":"agent-a"' in payload
        if request.method == "POST" and request.url.path == "/search":
            payload = request.read().decode()
            assert '"search_mode":"hybrid"' in payload
            assert '"agent_id":"agent-a"' in payload
        if request.method == "GET" and request.url.path == "/sessions/context":
            assert request.url.params["agent_id"] == "agent-a"
        if request.method == "GET" and request.url.path == "/users/u1/insights":
            assert request.url.params["agent_id"] == "agent-a"
        key = (request.method, request.url.path)
        return httpx.Response(200, json=responses[key])

    async def scenario():
        async with MemoryServiceClient("http://test", "u1", agent_id="agent-a") as client:
            client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test")

            ctx = await client.start_session()
            assert ctx.context == "ctx"
            assert client.session_id == "s1"
            assert ctx.agent_id == "agent-a"

            ctx2 = await client.get_context()
            assert ctx2.turn_count == 4

            turn = await client.store_turn("hello", "world")
            assert turn.turn_count == 5
            assert turn.pruning_triggered is True

            results = await client.search("risk", search_mode="hybrid")
            assert results == "found"

            insights = await client.get_insights()
            sessions = await client.get_sessions()
            assert insights == [{"id": "i1"}]
            assert sessions == [{"id": "s1"}]

            ended = await client.end_session()
            assert ended.synthesis_triggered is True
            assert client.session_id is None

    asyncio.run(scenario())


def test_memory_service_client_requires_open():
    client_module = importlib.import_module("client.memory_client")
    MemoryServiceClient = client_module.MemoryServiceClient

    client = MemoryServiceClient("http://test", "u1", agent_id="agent-a")

    try:
        _ = client.client
    except RuntimeError as exc:
        assert "async with" in str(exc)
    else:
        raise AssertionError("Expected MemoryServiceClient.client to require explicit open()")
