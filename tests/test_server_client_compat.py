import asyncio
import importlib

import httpx


def test_server_endpoints_map_current_memory_shapes(install_agent_framework_stubs):
    server_main = importlib.import_module("server.main")

    class FakeMemory:
        def __init__(self):
            self.session_id = "session-1"
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

        async def search(self, **kwargs):
            return "results"

        async def get_insights(self, limit=10):
            return [{"insight_text": "i1"}]

        async def get_sessions(self, limit=10):
            return [{"summary": "s1"}]

        async def close(self):
            return None

    class FakePool:
        def __init__(self):
            self.memory = FakeMemory()
            self.active_count = 1
            self.ephemeral_calls = 0
            self.pooled_calls = 0

        async def get_or_create(self, **kwargs):
            self.pooled_calls += 1
            return self.memory

        async def create_ephemeral(self, *args, **kwargs):
            self.ephemeral_calls += 1
            return self.memory

        async def get(self, user_id, session_id):
            return self.memory

        async def remove(self, user_id, session_id):
            return True

    server_main.session_pool = FakePool()
    server_main.start_time = server_main._utcnow()

    start = asyncio.run(server_main.start_session(server_main.StartSessionRequest(user_id="u1")))
    assert start.context == "ctx"
    assert start.insights_loaded is True
    assert start.recent_sessions_count == 5

    stored = asyncio.run(
        server_main.store_turn(
            server_main.StoreTurnRequest(
                user_id="u1",
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
            server_main.EndSessionRequest(user_id="u1", session_id="session-1"),
            background_tasks=server_main.BackgroundTasks(),
        )
    )
    assert ended.summary == "summary"
    assert ended.insights_count == 1
    assert ended.synthesis_triggered is True

    searched = asyncio.run(server_main.search_memory(server_main.SearchRequest(user_id="u1", query="risk")))
    assert searched.results == "results"

    insights = asyncio.run(server_main.get_user_insights("u1"))
    sessions = asyncio.run(server_main.get_user_sessions("u1"))
    assert insights["insights"] == [{"insight_text": "i1"}]
    assert sessions["sessions"] == [{"summary": "s1"}]
    assert server_main.session_pool.ephemeral_calls == 3


def test_server_exposes_get_only_context_route(install_agent_framework_stubs):
    server_main = importlib.import_module("server.main")

    assert hasattr(server_main, "get_context")
    assert not hasattr(server_main, "get_context_get")


def test_memory_service_client_parses_wire_shapes():
    client_module = importlib.import_module("client.memory_client")
    MemoryServiceClient = client_module.MemoryServiceClient

    responses = {
        ("POST", "/sessions/start"): {"session_id": "s1", "user_id": "u1", "context": "ctx", "insights_loaded": True, "recent_sessions_count": 2},
        ("GET", "/sessions/context"): {"context": "ctx2", "turn_count": 4},
        ("POST", "/sessions/turn"): {"success": True, "turn_count": 5, "pruning_triggered": True},
        ("POST", "/sessions/end"): {"success": True, "summary": "done", "insights_count": 2, "synthesis_triggered": True},
        ("POST", "/search"): {"results": "found", "query": "risk"},
        ("GET", "/users/u1/insights"): {"insights": [{"id": "i1"}]},
        ("GET", "/users/u1/sessions"): {"sessions": [{"id": "s1"}]},
    }

    def handler(request):
        key = (request.method, request.url.path)
        return httpx.Response(200, json=responses[key])

    async def scenario():
        async with MemoryServiceClient("http://test", "u1") as client:
            client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="http://test")

            ctx = await client.start_session()
            assert ctx.context == "ctx"
            assert client.session_id == "s1"

            ctx2 = await client.get_context()
            assert ctx2.turn_count == 4

            turn = await client.store_turn("hello", "world")
            assert turn.turn_count == 5
            assert turn.pruning_triggered is True

            results = await client.search("risk")
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

    client = MemoryServiceClient("http://test", "u1")

    try:
        _ = client.client
    except RuntimeError as exc:
        assert "async with" in str(exc)
    else:
        raise AssertionError("Expected MemoryServiceClient.client to require explicit open()")
