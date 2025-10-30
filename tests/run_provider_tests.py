"""
Simple test runner for CosmosMemoryProvider tests.
"""

import asyncio
import sys
from unittest.mock import Mock, AsyncMock, patch

# Add parent directory to path
sys.path.insert(0, 'C:\\testing\\agent_memory')

from agent_framework import ChatMessage, Context, Role
from memory.cosmos_memory_provider import CosmosMemoryProvider
from memory.provider_config import CosmosMemoryProviderConfig


def create_mock_cosmos_client():
    """Create a mock CosmosClient."""
    client = Mock()
    database = Mock()
    
    interactions_container = Mock()
    summaries_container = Mock()
    insights_container = Mock()
    
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
    embeddings_response = Mock()
    embeddings_response.data = [Mock(embedding=[0.1] * 1536)]
    client.embeddings = Mock()
    client.embeddings.create = Mock(return_value=embeddings_response)
    
    chat_response = Mock()
    chat_response.choices = [Mock(message=Mock(content="Test response"))]
    client.chat = Mock()
    client.chat.completions = Mock()
    client.chat.completions.create = Mock(return_value=chat_response)
    
    return client


async def test_init_with_connection_string():
    """Test initialization with connection string."""
    print("Testing: init_with_connection_string... ", end="")
    
    mock_openai = create_mock_openai_client()
    config = CosmosMemoryProviderConfig(trigger_reflection_on_end=False)
    
    with patch('memory.cosmos_memory_provider.CosmosAgentMemory') as MockMemory:
        mock_memory = AsyncMock()
        MockMemory.return_value = mock_memory
        
        provider = CosmosMemoryProvider(
            user_id="test_user",
            cosmos_connection_string="AccountEndpoint=https://test.documents.azure.com:443/;",
            openai_client=mock_openai,
            config=config
        )
        
        assert provider.user_id == "test_user"
        assert provider.config == config
        assert not provider._session_active
        print("✓ PASSED")


async def test_thread_created_starts_session():
    """Test that thread_created starts a session."""
    print("Testing: thread_created_starts_session... ", end="")
    
    mock_cosmos = create_mock_cosmos_client()
    mock_openai = create_mock_openai_client()
    config = CosmosMemoryProviderConfig(
        auto_manage_sessions=True,
        use_thread_as_session=True
    )
    
    with patch('memory.cosmos_memory_provider.CosmosAgentMemory') as MockMemory:
        mock_memory = AsyncMock()
        mock_memory.start_session = AsyncMock()
        MockMemory.return_value = mock_memory
        
        provider = CosmosMemoryProvider(
            user_id="test_user",
            cosmos_client=mock_cosmos,
            openai_client=mock_openai,
            config=config
        )
        
        thread_id = "thread_123"
        await provider.thread_created(thread_id)
        
        assert provider._current_thread_id == thread_id
        assert provider._session_active
        mock_memory.start_session.assert_called_once_with(session_id=thread_id)
        print("✓ PASSED")


async def test_invoking_with_longterm_insights():
    """Test context includes long-term insights."""
    print("Testing: invoking_with_longterm_insights... ", end="")
    
    mock_cosmos = create_mock_cosmos_client()
    mock_openai = create_mock_openai_client()
    config = CosmosMemoryProviderConfig(
        include_longterm_insights=True,
        include_recent_sessions=False,
        include_cumulative_summary=False,
        include_active_turns=False
    )
    
    with patch('memory.cosmos_memory_provider.CosmosAgentMemory') as MockMemory:
        mock_memory = AsyncMock()
        mock_memory.start_session = AsyncMock()
        
        # Mock orchestrator and memory keeper
        mock_orchestrator = Mock()
        mock_keeper = Mock()
        mock_init_context = Mock(
            longterm_insight="User is interested in retirement planning",
            recent_summaries=[]
        )
        mock_keeper.session_init_context = mock_init_context
        mock_keeper.cumulative_summary = None
        mock_keeper.get_active_context = Mock(return_value="")
        mock_orchestrator.memory_keeper = mock_keeper
        mock_memory._orchestrator = mock_orchestrator
        
        MockMemory.return_value = mock_memory
        
        provider = CosmosMemoryProvider(
            user_id="test_user",
            cosmos_client=mock_cosmos,
            openai_client=mock_openai,
            config=config
        )
        
        await provider.thread_created("thread_123")
        
        messages = [ChatMessage(role=Role.USER, text="Hello")]
        context = await provider.invoking(messages)
        
        assert context.messages is not None
        assert len(context.messages) == 1
        assert "retirement planning" in context.messages[0].text
        assert "Long-term User Profile" in context.messages[0].text
        print("✓ PASSED")


async def test_invoking_without_session_returns_empty():
    """Test invoking without session returns empty Context."""
    print("Testing: invoking_without_session_returns_empty... ", end="")
    
    mock_cosmos = create_mock_cosmos_client()
    mock_openai = create_mock_openai_client()
    config = CosmosMemoryProviderConfig()
    
    with patch('memory.cosmos_memory_provider.CosmosAgentMemory') as MockMemory:
        mock_memory = AsyncMock()
        MockMemory.return_value = mock_memory
        
        provider = CosmosMemoryProvider(
            user_id="test_user",
            cosmos_client=mock_cosmos,
            openai_client=mock_openai,
            config=config
        )
        
        # Don't start session
        messages = [ChatMessage(role=Role.USER, text="Hello")]
        context = await provider.invoking(messages)
        
        assert context.messages is None or len(context.messages) == 0
        assert context.instructions is None
        print("✓ PASSED")


async def test_invoked_stores_messages():
    """Test that invoked stores user and assistant messages."""
    print("Testing: invoked_stores_messages... ", end="")
    
    mock_cosmos = create_mock_cosmos_client()
    mock_openai = create_mock_openai_client()
    config = CosmosMemoryProviderConfig()
    
    with patch('memory.cosmos_memory_provider.CosmosAgentMemory') as MockMemory:
        mock_memory = AsyncMock()
        mock_memory.start_session = AsyncMock()
        mock_memory.add_turn = AsyncMock()
        MockMemory.return_value = mock_memory
        
        provider = CosmosMemoryProvider(
            user_id="test_user",
            cosmos_client=mock_cosmos,
            openai_client=mock_openai,
            config=config
        )
        
        await provider.thread_created("thread_123")
        
        request_messages = [ChatMessage(role=Role.USER, text="What's a Roth IRA?")]
        response_messages = [ChatMessage(role=Role.ASSISTANT, text="A Roth IRA is...")]
        
        await provider.invoked(request_messages, response_messages)
        
        mock_memory.add_turn.assert_called_once_with(
            user_message="What's a Roth IRA?",
            assistant_message="A Roth IRA is..."
        )
        print("✓ PASSED")


async def test_invoked_skips_memory_context():
    """Test that invoked skips memory context messages."""
    print("Testing: invoked_skips_memory_context... ", end="")
    
    mock_cosmos = create_mock_cosmos_client()
    mock_openai = create_mock_openai_client()
    config = CosmosMemoryProviderConfig()
    
    with patch('memory.cosmos_memory_provider.CosmosAgentMemory') as MockMemory:
        mock_memory = AsyncMock()
        mock_memory.start_session = AsyncMock()
        mock_memory.add_turn = AsyncMock()
        MockMemory.return_value = mock_memory
        
        provider = CosmosMemoryProvider(
            user_id="test_user",
            cosmos_client=mock_cosmos,
            openai_client=mock_openai,
            config=config
        )
        
        await provider.thread_created("thread_123")
        
        # Include memory context message that should be skipped
        request_messages = [
            ChatMessage(role=Role.USER, text="## Memory Context\nUser profile..."),
            ChatMessage(role=Role.USER, text="What's a Roth IRA?")
        ]
        response_messages = [ChatMessage(role=Role.ASSISTANT, text="A Roth IRA is...")]
        
        await provider.invoked(request_messages, response_messages)
        
        # Should only store the actual user question
        # The provider should skip the memory context message and only store the real user message
        mock_memory.add_turn.assert_called_once_with(
            user_message="What's a Roth IRA?",
            assistant_message="A Roth IRA is..."
        )
        print("✓ PASSED")


async def test_context_manager():
    """Test context manager functionality."""
    print("Testing: context_manager... ", end="")
    
    mock_cosmos = create_mock_cosmos_client()
    mock_openai = create_mock_openai_client()
    config = CosmosMemoryProviderConfig()
    
    with patch('memory.cosmos_memory_provider.CosmosAgentMemory') as MockMemory:
        mock_memory = AsyncMock()
        mock_memory.start_session = AsyncMock()
        mock_memory.end_session = AsyncMock(return_value={"session_id": "test"})
        mock_memory.__aenter__ = AsyncMock(return_value=mock_memory)
        mock_memory.__aexit__ = AsyncMock()
        MockMemory.return_value = mock_memory
        
        provider_ref = None
        async with CosmosMemoryProvider(
            user_id="test_user",
            cosmos_client=mock_cosmos,
            openai_client=mock_openai,
            config=config
        ) as provider:
            provider_ref = provider
            await provider.thread_created("thread_123")
            assert provider._session_active
        
        # After exit, session should be ended
        assert not provider_ref._session_active
        mock_memory.end_session.assert_called_once()
        print("✓ PASSED")


def test_get_status():
    """Test get_status method."""
    print("Testing: get_status... ", end="")
    
    mock_cosmos = create_mock_cosmos_client()
    mock_openai = create_mock_openai_client()
    config = CosmosMemoryProviderConfig()
    
    with patch('memory.cosmos_memory_provider.CosmosAgentMemory') as MockMemory:
        mock_memory = AsyncMock()
        MockMemory.return_value = mock_memory
        
        provider = CosmosMemoryProvider(
            user_id="test_user",
            cosmos_client=mock_cosmos,
            openai_client=mock_openai,
            config=config
        )
        
        status = provider.get_status()
        
        assert status["user_id"] == "test_user"
        assert status["session_active"] is False
        assert "config" in status
        print("✓ PASSED")


async def main():
    """Run all tests."""
    print("=" * 70)
    print("Running CosmosMemoryProvider Tests")
    print("=" * 70)
    print()
    
    # Run tests
    await test_init_with_connection_string()
    await test_thread_created_starts_session()
    await test_invoking_with_longterm_insights()
    await test_invoking_without_session_returns_empty()
    await test_invoked_stores_messages()
    await test_invoked_skips_memory_context()
    await test_context_manager()
    test_get_status()
    
    print()
    print("=" * 70)
    print("All tests completed successfully! ✓")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
