import importlib


def test_active_modules_import_with_agent_framework_stubs(install_agent_framework_stubs):
    modules = [
        "memory",
        "memory.core.agent_memory",
        "memory.core.orchestrator",
        "memory.core.fact_retrieval",
        "server.main",
        "client.memory_client",
        "agent.single_agent",
        "demo.03_agent_driven",
    ]

    for name in modules:
        importlib.import_module(name)
