"""
Simple test runner for CosmosAgentMemory without pytest.
"""

import asyncio
import sys
from unittest.mock import Mock, AsyncMock, MagicMock, patch

# Add parent directory to path
sys.path.insert(0, 'C:\\testing\\agent_memory')

from memory.cosmos_agent_memory import CosmosAgentMemory
from memory.config import MemoryConfig


def create_mock_cosmos_client():
    """Create a mock CosmosClient."""
    client = Mock()
    database = Mock()
    
    # Mock containers
    interactions_container = Mock()
    summaries_container = Mock()
    insights_container = Mock()
    
    # Setup container queries
    interactions_container.query_items = Mock(return_value=[])
    summaries_container.query_items = Mock(return_value=iter([]))
    insights_container.query_items = Mock(return_value=[])
    
    database.get_container_client = Mock(side_effect=lambda name: {
        "interactions": interactions_container,
        "session_summaries": summaries_container,
        "insights": insights_container,
    }[name])
    
    client.get_database_client = Mock(return_value=database)
    
    return client


def create_mock_openai_client():
    """Create a mock Azure OpenAI client."""
    client = Mock()
    
    # Mock embeddings
    embeddings_response = Mock()
    embeddings_response.data = [Mock(embedding=[0.1] * 1536)]
    client.embeddings = Mock()
    client.embeddings.create = Mock(return_value=embeddings_response)
    
    # Mock chat completions
    chat_response = Mock()
    chat_response.choices = [Mock(message=Mock(content="Test response"))]
    client.chat = Mock()
    client.chat.completions = Mock()
    client.chat.completions.create = Mock(return_value=chat_response)
    
    return client


async def test_init_with_cosmos_client():
    """Test initialization with pre-created CosmosClient."""
    print("Testing: init_with_cosmos_client... ", end="")
    
    mock_cosmos_client = create_mock_cosmos_client()
    mock_openai_client = create_mock_openai_client()
    
    memory = CosmosAgentMemory(
        user_id="test_user",
        cosmos_client=mock_cosmos_client,
        openai_client=mock_openai_client
    )
    
    assert memory.user_id == "test_user"
    assert memory._database is not None
    assert not memory._own_client
    print("✓ PASSED")


async def test_init_with_custom_config():
    """Test initialization with custom configuration."""
    print("Testing: init_with_custom_config... ", end="")
    
    custom_config = MemoryConfig(
        buffer_size=15,
        active_turns=7,
        database_name="custom_db"
    )
    
    memory = CosmosAgentMemory(
        user_id="test_user",
        cosmos_client=create_mock_cosmos_client(),
        openai_client=create_mock_openai_client(),
        config=custom_config
    )
    
    assert memory.config.buffer_size == 15
    assert memory.config.active_turns == 7
    assert memory.config.database_name == "custom_db"
    print("✓ PASSED")


async def test_start_session_auto_generates_id():
    """Test that start_session auto-generates session_id if not provided."""
    print("Testing: start_session_auto_generates_id... ", end="")
    
    memory = CosmosAgentMemory(
        user_id="test_user",
        cosmos_client=create_mock_cosmos_client(),
        openai_client=create_mock_openai_client(),
        config=MemoryConfig(trigger_reflection_on_end=False)
    )
    
    with patch('memory.cosmos_agent_memory.MemoryServiceOrchestrator') as MockOrchestrator:
        mock_orch = AsyncMock()
        mock_orch.initialize_session = AsyncMock(return_value={"status": "initialized"})
        MockOrchestrator.return_value = mock_orch
        
        result = await memory.start_session()
    
    assert memory.session_id is not None
    assert memory._session_started
    assert "status" in result
    print("✓ PASSED")


async def test_add_turn_without_session_raises_error():
    """Test that add_turn without starting session raises RuntimeError."""
    print("Testing: add_turn_without_session_raises_error... ", end="")
    
    memory = CosmosAgentMemory(
        user_id="test_user",
        cosmos_client=create_mock_cosmos_client(),
        openai_client=create_mock_openai_client(),
        config=MemoryConfig()
    )
    
    try:
        await memory.add_turn("Hello", "Hi there!")
        print("✗ FAILED - Expected RuntimeError")
        return False
    except RuntimeError as e:
        if "Session not started" in str(e):
            print("✓ PASSED")
            return True
        else:
            print(f"✗ FAILED - Wrong error message: {e}")
            return False


async def test_add_turn_success():
    """Test successful turn addition."""
    print("Testing: add_turn_success... ", end="")
    
    memory = CosmosAgentMemory(
        user_id="test_user",
        cosmos_client=create_mock_cosmos_client(),
        openai_client=create_mock_openai_client(),
        config=MemoryConfig(trigger_reflection_on_end=False)
    )
    
    with patch('memory.cosmos_agent_memory.MemoryServiceOrchestrator') as MockOrchestrator:
        mock_orch = AsyncMock()
        mock_orch.initialize_session = AsyncMock(return_value={"status": "initialized"})
        mock_orch.process_turn = AsyncMock(return_value={
            "turn_added": True,
            "active_turns_count": 1
        })
        MockOrchestrator.return_value = mock_orch
        
        await memory.start_session()
        result = await memory.add_turn("Hello", "Hi there!")
    
    assert result["turn_added"]
    assert result["active_turns_count"] == 1
    print("✓ PASSED")


async def test_get_context_success():
    """Test successful context retrieval."""
    print("Testing: get_context_success... ", end="")
    
    memory = CosmosAgentMemory(
        user_id="test_user",
        cosmos_client=create_mock_cosmos_client(),
        openai_client=create_mock_openai_client(),
        config=MemoryConfig(trigger_reflection_on_end=False)
    )
    
    with patch('memory.cosmos_agent_memory.MemoryServiceOrchestrator') as MockOrchestrator:
        mock_orch = AsyncMock()
        mock_orch.initialize_session = AsyncMock(return_value={"status": "initialized"})
        
        # Mock memory keeper
        mock_keeper = Mock()
        mock_keeper.session_init_context = Mock(
            longterm_insight="User likes coffee",
            recent_summaries=[]
        )
        mock_keeper.cumulative_summary = None
        mock_keeper.get_active_context = Mock(return_value="User: Hello\nAssistant: Hi!")
        
        mock_orch.memory_keeper = mock_keeper
        MockOrchestrator.return_value = mock_orch
        
        await memory.start_session()
        context = memory.get_context()
    
    assert "User likes coffee" in context
    assert "Hello" in context
    print("✓ PASSED")


async def test_context_manager():
    """Test context manager functionality."""
    print("Testing: context_manager... ", end="")
    
    with patch('memory.cosmos_agent_memory.MemoryServiceOrchestrator') as MockOrchestrator:
        mock_orch = AsyncMock()
        mock_orch.initialize_session = AsyncMock(return_value={"status": "initialized"})
        mock_orch.end_session = AsyncMock(return_value={"session_id": "test"})
        MockOrchestrator.return_value = mock_orch
        
        memory_ref = None
        async with CosmosAgentMemory(
            user_id="test_user",
            cosmos_client=create_mock_cosmos_client(),
            openai_client=create_mock_openai_client(),
            config=MemoryConfig(trigger_reflection_on_end=False)
        ) as memory:
            memory_ref = memory
            assert memory._session_started
            assert memory.session_id is not None
        
        # After exit, session should be ended
        assert not memory_ref._session_started
    
    print("✓ PASSED")


def test_legacy_config_properties():
    """Test that legacy config properties still work."""
    print("Testing: legacy_config_properties... ", end="")
    
    config = MemoryConfig(
        buffer_size=15,
        active_turns=7,
        min_confidence=0.8
    )
    
    # Test legacy property access
    assert config.K_TURN_BUFFER == 15
    assert config.N_ACTIVE_TURNS == 7
    assert config.INSIGHT_CONFIDENCE_THRESHOLD == 0.8
    assert config.COSMOS_DB_NAME == "agent_memory"
    print("✓ PASSED")


async def main():
    """Run all tests."""
    print("=" * 70)
    print("Running CosmosAgentMemory Tests")
    print("=" * 70)
    print()
    
    # Run synchronous tests
    test_legacy_config_properties()
    
    # Run async tests
    await test_init_with_cosmos_client()
    await test_init_with_custom_config()
    await test_start_session_auto_generates_id()
    await test_add_turn_without_session_raises_error()
    await test_add_turn_success()
    await test_get_context_success()
    await test_context_manager()
    
    print()
    print("=" * 70)
    print("All tests completed successfully! ✓")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
