import asyncio
import os
import socket
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from dotenv import dotenv_values
from openai import AzureOpenAI

from client.memory_client import MemoryServiceClient
from memory.core.agent_memory import AgentMemory, AgentMemoryConfig
from memory.db.factory import DatabaseType


RUN_ID = os.getenv("LIVE_TEST_RUN_ID") or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
REPO_ROOT = Path(__file__).resolve().parents[1]
AZURE_OPENAI_KEYS = {
    "AZURE_OPENAI_API_KEY",
    "AZURE_OPENAI_API_VERSION",
    "AZURE_OPENAI_CHAT_DEPLOYMENT",
    "AZURE_OPENAI_CHAT_DEPLOYMENT_NAME",
    "AZURE_OPENAI_EMBEDDING_DEPLOYMENT",
    "AZURE_OPENAI_EMB_DEPLOYMENT",
    "AZURE_OPENAI_ENDPOINT",
    "AZURE_OPENAI_PROCESSING_MODEL",
    "AZURE_OPENAI_REASONING_MODEL",
}
LIVE_AZD_KEYS = [
    "AZURE_AI_SEARCH_API_KEY",
    "AZURE_AI_SEARCH_ENDPOINT",
    "AZURE_AI_SEARCH_INDEX_PREFIX",
    "POSTGRES_CONNECTION_STRING",
    "POSTGRES_DATABASE",
    "POSTGRES_HOST",
]


def _azd_env_value(name: str) -> str | None:
    try:
        result = subprocess.run(
            ["azd", "env", "get-value", name],
            check=False,
            capture_output=True,
            text=True,
            cwd=str(REPO_ROOT),
        )
    except FileNotFoundError:
        return None

    if result.returncode != 0:
        return None

    value = result.stdout.strip()
    return value or None


def _load_live_env() -> dict[str, str]:
    env = {}
    primary_env_path = REPO_ROOT / ".env"
    azd_env_path = REPO_ROOT / ".azure" / "agent-memory" / ".env"

    if primary_env_path.exists():
        env.update({k: v for k, v in dotenv_values(primary_env_path).items() if v})
    if azd_env_path.exists():
        for key, value in dotenv_values(azd_env_path).items():
            if not value:
                continue
            if key in AZURE_OPENAI_KEYS and key in env:
                continue
            env[key] = value
    for key in LIVE_AZD_KEYS:
        value = _azd_env_value(key)
        if value:
            env[key] = value
    env.update({k: v for k, v in os.environ.items() if v})
    return env


def _require_keys(env: dict[str, str], keys: list[str]) -> None:
    missing = [key for key in keys if not env.get(key)]
    if missing:
        pytest.skip(f"Missing live test configuration: {', '.join(missing)}")


def _openai_client(env: dict[str, str]) -> AzureOpenAI:
    endpoint = env.get("AZURE_OPENAI_ENDPOINT")
    api_key = env.get("AZURE_OPENAI_API_KEY")
    api_version = env.get("AZURE_OPENAI_API_VERSION", "2025-04-01-preview")
    if not endpoint or not api_key:
        pytest.skip("Azure OpenAI endpoint/api key not configured for live tests")
    return AzureOpenAI(azure_endpoint=endpoint, api_key=api_key, api_version=api_version)


def _config(env: dict[str, str]) -> AgentMemoryConfig:
    chat_model = (
        env.get("AZURE_OPENAI_REASONING_MODEL")
        or env.get("AZURE_OPENAI_CHAT_DEPLOYMENT")
        or env.get("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
        or "gpt-5-chat"
    )
    processing_model = env.get("AZURE_OPENAI_PROCESSING_MODEL") or chat_model
    embedding_model = (
        env.get("AZURE_OPENAI_EMB_DEPLOYMENT")
        or env.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT")
        or "text-embedding-ada-002"
    )
    return AgentMemoryConfig(
        reasoning_model=chat_model,
        processing_model=processing_model,
        embedding_model=embedding_model,
        embedding_dimensions=1536,
    )


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


async def _exercise_direct_memory(
    *,
    backend_name: str,
    env: dict[str, str],
    db_type: DatabaseType,
    memory_kwargs: dict,
) -> None:
    openai_client = _openai_client(env)
    config = _config(env)
    shared_user_id = f"live-user-{backend_name}-{RUN_ID}"
    agent_a = f"agent-a-{backend_name}"
    agent_b = f"agent-b-{backend_name}"
    token_a = f"harbor-a-{backend_name}-{RUN_ID}"
    token_b = f"harbor-b-{backend_name}-{RUN_ID}"

    async def run_session(agent_id: str, token: str, beverage: str) -> AgentMemory:
        memory = AgentMemory(
            user_id=shared_user_id,
            agent_id=agent_id,
            openai_client=openai_client,
            db_type=db_type,
            config=config,
            **memory_kwargs,
        )
        await memory.start_session()
        await memory.add_turn(
            f"My enduring preference token is {token}. I strongly prefer {beverage}.",
            f"Understood. I will remember that your preference token is {token} and you prefer {beverage}.",
        )
        await memory.add_turn(
            f"My long-term goal is to plan a trip tied to {token}.",
            f"I noted that your goal is associated with {token}.",
        )
        context = await memory.get_context()
        assert context
        result = await memory.end_session()
        assert result["session_summary"]
        return memory

    memory_a = await run_session(agent_a, token_a, "hibiscus tea")
    memory_b = await run_session(agent_b, token_b, "oolong tea")

    try:
        sessions_a = await memory_a.get_sessions(limit=5)
        sessions_b = await memory_b.get_sessions(limit=5)
        assert sessions_a, "Expected persisted sessions for agent A"
        assert sessions_b, "Expected persisted sessions for agent B"
        assert all(session.get("agent_id") == agent_a for session in sessions_a)
        assert all(session.get("agent_id") == agent_b for session in sessions_b)

        insights_a = await memory_a.get_insights(limit=10)
        insights_b = await memory_b.get_insights(limit=10)
        assert insights_a, "Expected at least one insight for agent A"
        assert insights_b, "Expected at least one insight for agent B"

        search_a = await memory_a.search(token_a, top_k=3, search_summaries=True)
        search_b = await memory_b.search(token_b, top_k=3, search_summaries=True)
        assert "hibiscus tea" in search_a
        assert "oolong tea" not in search_a
        assert "oolong tea" in search_b
        assert "hibiscus tea" not in search_b
    finally:
        await memory_a.close()
        await memory_b.close()


async def _wait_for_server(base_url: str, timeout_seconds: int = 240) -> None:
    deadline = time.time() + timeout_seconds
    async with httpx.AsyncClient(timeout=10.0) as client:
        while time.time() < deadline:
            try:
                response = await client.get(f"{base_url}/health")
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            await asyncio.sleep(1)
    raise RuntimeError(f"Server at {base_url} did not become healthy in time")


async def _exercise_server_client(
    *,
    backend_name: str,
    env: dict[str, str],
    backend_env: dict[str, str],
) -> None:
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    process_env = os.environ.copy()
    process_env.update(env)
    process_env.update(backend_env)
    process_env["PYTHONPATH"] = str(REPO_ROOT)
    process_env["AGENT_MEMORY_DB_TYPE"] = backend_env["AGENT_MEMORY_DB_TYPE"]
    process_env["AZURE_OPENAI_REASONING_MODEL"] = (
        env.get("AZURE_OPENAI_REASONING_MODEL")
        or env.get("AZURE_OPENAI_CHAT_DEPLOYMENT")
        or env.get("AZURE_OPENAI_CHAT_DEPLOYMENT_NAME")
        or "gpt-5-chat"
    )
    process_env["AZURE_OPENAI_PROCESSING_MODEL"] = (
        env.get("AZURE_OPENAI_PROCESSING_MODEL")
        or process_env["AZURE_OPENAI_REASONING_MODEL"]
    )

    command = [sys.executable, "-m", "uvicorn", "server.main:app", "--host", "127.0.0.1", "--port", str(port)]
    log_fd, log_path = tempfile.mkstemp(prefix=f"agent-memory-live-{backend_name}-", suffix=".log")
    os.close(log_fd)
    log_file = open(log_path, "w", encoding="utf-8")
    proc = subprocess.Popen(
        command,
        cwd=str(REPO_ROOT),
        env=process_env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
    )

    client_a = None
    client_b = None
    completed_successfully = False
    try:
        await _wait_for_server(base_url)
        user_id = f"live-http-user-{backend_name}-{RUN_ID}"
        agent_a = f"http-agent-a-{backend_name}"
        agent_b = f"http-agent-b-{backend_name}"
        token_a = f"server-a-{backend_name}-{RUN_ID}"
        token_b = f"server-b-{backend_name}-{RUN_ID}"

        async with MemoryServiceClient(base_url, user_id, agent_id=agent_a, timeout=240.0) as client_a:
            health = await client_a.health_check()
            assert health["status"] == "healthy"
            ctx = await client_a.start_session()
            assert ctx.agent_id == agent_a
            await client_a.store_turn(
                f"My persistent server token is {token_a}. I prefer jasmine tea.",
                f"Noted. Your persistent token is {token_a} and you prefer jasmine tea.",
            )
            await client_a.store_turn(
                f"My follow-up goal is linked to {token_a}.",
                f"I also noted the goal associated with {token_a}.",
            )
            ctx2 = await client_a.get_context()
            assert ctx2.turn_count >= 2
            end_a = await client_a.end_session()
            assert end_a.summary

        async with MemoryServiceClient(base_url, user_id, agent_id=agent_b, timeout=240.0) as client_b:
            await client_b.start_session()
            await client_b.store_turn(
                f"My persistent server token is {token_b}. I prefer genmaicha tea.",
                f"Noted. Your persistent token is {token_b} and you prefer genmaicha tea.",
            )
            await client_b.store_turn(
                f"My follow-up goal is linked to {token_b}.",
                f"I also noted the goal associated with {token_b}.",
            )
            end_b = await client_b.end_session()
            assert end_b.summary

            search_b = await client_b.search(token_b, search_summaries=True)
            assert "genmaicha tea" in search_b
            assert "jasmine tea" not in search_b

            insights_b = await client_b.get_insights()
            sessions_b = await client_b.get_sessions()
            assert insights_b
            assert sessions_b

        async with MemoryServiceClient(base_url, user_id, agent_id=agent_a, timeout=240.0) as verifier_a:
            search_a = await verifier_a.search(token_a, search_summaries=True)
            sessions_a = await verifier_a.get_sessions()
            assert "jasmine tea" in search_a
            assert "genmaicha tea" not in search_a
            assert sessions_a
            assert all(session.get("agent_id") == agent_a for session in sessions_a)
        completed_successfully = True
    finally:
        log_file.flush()
        log_file.close()
        proc.terminate()
        try:
            proc.wait(timeout=20)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)
        if not completed_successfully and proc.returncode not in (0, -15):
            output = Path(log_path).read_text(encoding="utf-8", errors="replace")
            raise AssertionError(f"Server exited unexpectedly ({proc.returncode}). Output:\n{output}")


@pytest.mark.live
def test_live_azure_ai_search_direct_backend():
    env = _load_live_env()
    _require_keys(
        env,
        [
            "AZURE_AI_SEARCH_ENDPOINT",
            "AZURE_AI_SEARCH_API_KEY",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_API_KEY",
        ],
    )
    asyncio.run(
        _exercise_direct_memory(
            backend_name="azure-search",
            env=env,
            db_type=DatabaseType.AZURE_AI_SEARCH,
            memory_kwargs={
                "search_endpoint": env["AZURE_AI_SEARCH_ENDPOINT"],
                "search_api_key": env["AZURE_AI_SEARCH_API_KEY"],
                "search_index_prefix": env.get("AZURE_AI_SEARCH_INDEX_PREFIX", "agent-memory"),
            },
        )
    )


@pytest.mark.live
def test_live_postgresql_direct_backend():
    env = _load_live_env()
    _require_keys(
        env,
        [
            "POSTGRES_CONNECTION_STRING",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_API_KEY",
        ],
    )
    asyncio.run(
        _exercise_direct_memory(
            backend_name="postgresql",
            env=env,
            db_type=DatabaseType.POSTGRESQL,
            memory_kwargs={
                "postgres_connection_string": env["POSTGRES_CONNECTION_STRING"],
            },
        )
    )


@pytest.mark.live
def test_live_azure_ai_search_server_client():
    env = _load_live_env()
    _require_keys(
        env,
        [
            "AZURE_AI_SEARCH_ENDPOINT",
            "AZURE_AI_SEARCH_API_KEY",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_API_KEY",
        ],
    )
    asyncio.run(
        _exercise_server_client(
            backend_name="azure-search",
            env=env,
            backend_env={
                "AGENT_MEMORY_DB_TYPE": "azure_ai_search",
                "AZURE_AI_SEARCH_ENDPOINT": env["AZURE_AI_SEARCH_ENDPOINT"],
                "AZURE_AI_SEARCH_API_KEY": env["AZURE_AI_SEARCH_API_KEY"],
                "AZURE_AI_SEARCH_INDEX_PREFIX": env.get("AZURE_AI_SEARCH_INDEX_PREFIX", "agent-memory"),
            },
        )
    )


@pytest.mark.live
def test_live_postgresql_server_client():
    env = _load_live_env()
    _require_keys(
        env,
        [
            "POSTGRES_CONNECTION_STRING",
            "AZURE_OPENAI_ENDPOINT",
            "AZURE_OPENAI_API_KEY",
        ],
    )
    asyncio.run(
        _exercise_server_client(
            backend_name="postgresql",
            env=env,
            backend_env={
                "AGENT_MEMORY_DB_TYPE": "postgresql",
                "POSTGRES_CONNECTION_STRING": env["POSTGRES_CONNECTION_STRING"],
            },
        )
    )
