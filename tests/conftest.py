import importlib
import sys
import types

import pytest


@pytest.fixture
def install_agent_framework_stubs(monkeypatch):
    """Install lightweight Agent Framework stubs for import-time tests."""

    class StubBaseContextProvider:
        def __init__(self, source_id: str = "stub") -> None:
            self.source_id = source_id

    class StubSessionContext:
        pass

    class StubAgentSession:
        def __init__(self, state=None):
            self._state = state or {}

        def to_dict(self):
            return self._state

        @classmethod
        def from_dict(cls, state):
            return cls(state)

    class StubAgent:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def run(self, *args, **kwargs):
            return types.SimpleNamespace(text="stub-response")

        def create_session(self):
            return StubAgentSession()

    class StubMCPStreamableHTTPTool:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.session = None

    def stub_tool(*args, **kwargs):
        def decorator(func):
            return func
        return decorator

    class StubAzureOpenAIChatClient:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    agent_framework = types.ModuleType("agent_framework")
    agent_framework.Agent = StubAgent
    agent_framework.tool = stub_tool
    agent_framework.BaseContextProvider = StubBaseContextProvider
    agent_framework.SessionContext = StubSessionContext
    agent_framework.AgentSession = StubAgentSession
    agent_framework.MCPStreamableHTTPTool = StubMCPStreamableHTTPTool

    agent_framework_azure = types.ModuleType("agent_framework.azure")
    agent_framework_azure.AzureOpenAIChatClient = StubAzureOpenAIChatClient

    class StubHTTPException(Exception):
        def __init__(self, status_code: int, detail: str):
            super().__init__(detail)
            self.status_code = status_code
            self.detail = detail

    class StubBackgroundTasks:
        def __init__(self):
            self.tasks = []

        def add_task(self, func, *args, **kwargs):
            self.tasks.append((func, args, kwargs))

    class StubFastAPI:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def middleware(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

        def get(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

        def post(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

    fastapi = types.ModuleType("fastapi")
    fastapi.FastAPI = StubFastAPI
    fastapi.HTTPException = StubHTTPException
    fastapi.BackgroundTasks = StubBackgroundTasks
    fastapi.Request = object

    fastapi_responses = types.ModuleType("fastapi.responses")

    class StubJSONResponse:
        def __init__(self, status_code: int, content: dict):
            self.status_code = status_code
            self.content = content

    fastapi_responses.JSONResponse = StubJSONResponse

    monkeypatch.setitem(sys.modules, "agent_framework", agent_framework)
    monkeypatch.setitem(sys.modules, "agent_framework.azure", agent_framework_azure)
    monkeypatch.setitem(sys.modules, "fastapi", fastapi)
    monkeypatch.setitem(sys.modules, "fastapi.responses", fastapi_responses)

    for name in list(sys.modules):
        if name.startswith(("memory", "server", "client", "agent.")):
            sys.modules.pop(name, None)

    importlib.invalidate_caches()

    return {
        "Agent": StubAgent,
        "AgentSession": StubAgentSession,
        "BaseContextProvider": StubBaseContextProvider,
        "AzureOpenAIChatClient": StubAzureOpenAIChatClient,
        "MCPStreamableHTTPTool": StubMCPStreamableHTTPTool,
    }
