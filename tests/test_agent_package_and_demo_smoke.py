import asyncio
import importlib


def test_single_agent_helpers_construct_with_stubs(monkeypatch, install_agent_framework_stubs):
    monkeypatch.setenv("MCP_SERVER_URI", "https://mcp.example.test")

    single_agent = importlib.import_module("agent.single_agent")
    agent = single_agent.Agent(state_store={}, session_id="s1", access_token="token-1")

    headers = agent._build_headers()
    tools = asyncio.run(agent._maybe_create_tools(headers))

    assert headers["Authorization"] == "Bearer token-1"
    assert len(tools) == 1
    assert tools[0].kwargs["url"] == "https://mcp.example.test"


def test_demo_agent_driven_memory_tools_call_memory(install_agent_framework_stubs):
    demo = importlib.import_module("demo.03_agent_driven")

    class FakeMemory:
        async def search(self, *args, **kwargs):
            return "search-results"

        async def get_insights(self, limit=10):
            return [{"insight_text": "Remembered", "category": "general", "confidence": 0.8}]

    search_memory, get_patient_profile = demo.create_memory_tools(FakeMemory())

    assert asyncio.run(search_memory("allergies")) == "search-results"

    profile = asyncio.run(get_patient_profile())
    assert "Remembered" in profile
