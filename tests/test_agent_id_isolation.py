import asyncio
import importlib

from memory.db.factory import DatabaseType


def test_session_pool_scopes_sessions_by_agent(monkeypatch, install_agent_framework_stubs):
    server_main = importlib.import_module("server.main")

    class FakeMemory:
        def __init__(self, user_id, agent_id, **kwargs):
            self.user_id = user_id
            self.agent_id = agent_id
            self.session_id = kwargs["session_id"]
            self.started = 0
            self.closed = 0

        async def start_session(self, restore=False):
            self.started += 1
            return {"session_id": self.session_id}

        async def end_session(self, trigger_reflection=False):
            return {}

        async def close(self):
            self.closed += 1

    monkeypatch.setattr(server_main, "AgentMemory", FakeMemory)

    pool = server_main.SessionPool(
        openai_client=object(),
        db_type=DatabaseType.SQLITE,
        db_path=":memory:",
        max_sessions=10,
        session_ttl_minutes=30,
    )

    memory_a = asyncio.run(pool.get_or_create("user-1", "agent-a", session_id="session-1", start_session=False))
    memory_b = asyncio.run(pool.get_or_create("user-1", "agent-b", session_id="session-1", start_session=False))

    assert memory_a is not memory_b
    assert pool.active_count == 2
    assert asyncio.run(pool.get("user-1", "agent-a", "session-1")) is memory_a
    assert asyncio.run(pool.get("user-1", "agent-b", "session-1")) is memory_b
    assert asyncio.run(pool.get("user-1", "agent-c", "session-1")) is None
