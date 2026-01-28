"""
Quickstart: Unified Agent Memory Usage
======================================

This demonstrates the new unified AgentMemory API that works with any backend.

The same code works with SQLite (default) or CosmosDB - just change db_type.

Run: python demos/quickstart/unified_usage.py
"""

import asyncio
import os
import sys
from pathlib import Path

# Setup paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / '.env')

from openai import AzureOpenAI
from memory import AgentMemory, AgentMemoryConfig, create_agent_memory
from memory.db.factory import DatabaseType


async def example_sqlite():
    """Example 1: SQLite backend (default, no server required)."""
    print("=" * 70)
    print("Example 1: SQLite Backend (Default)")
    print("=" * 70)
    
    # Create OpenAI client
    openai_client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    )
    
    # Create config with models from environment
    config = AgentMemoryConfig(
        reasoning_model=os.getenv("AZURE_OPENAI_REASONING_MODEL", "gpt-4o"),
        processing_model=os.getenv("AZURE_OPENAI_PROCESSING_MODEL", "gpt-4o-mini"),
        embedding_model=os.getenv("AZURE_OPENAI_EMB_DEPLOYMENT", "text-embedding-ada-002")
    )
    
    # Initialize memory with SQLite (default)
    # No external services required!
    memory = AgentMemory(
        user_id="demo_user_123",
        openai_client=openai_client,
        db_path="demo_unified.db",  # SQLite file
        config=config
    )
    
    try:
        # Start session
        session_info = await memory.start_session()
        print(f"\n✅ Session started: {memory.session_id[:8]}...")
        
        # Add conversation turns
        await memory.add_turn(
            "Hello! I'm interested in retirement planning.",
            "Great! I'd be happy to help you with retirement planning. What specific aspects are you interested in?"
        )
        print("   Added turn 1: Retirement planning intro")
        
        await memory.add_turn(
            "I want to understand Roth IRA options. I'm 35 years old.",
            "A Roth IRA is an excellent choice at 35! Contributions are made with after-tax dollars, but qualified withdrawals are tax-free in retirement..."
        )
        print("   Added turn 2: Roth IRA discussion")
        
        await memory.add_turn(
            "How much should I contribute annually?",
            "For 2025, the contribution limit is $7,000 (or $8,000 if you're 50+). I recommend maxing it out if possible, which would be about $583/month."
        )
        print("   Added turn 3: Contribution discussion")
        
        # Get memory context (for adding to AI prompt)
        context = memory.get_context()
        print(f"\n📝 Memory Context Preview:\n{context[:300]}...")
        
        # Search memory for specific facts
        facts = await memory.search("What age is the user?")
        print(f"\n🔍 Search Result:\n{facts}")
        
        # End session (extracts summary and insights)
        result = await memory.end_session()
        print(f"\n✅ Session ended")
        print(f"   Summary: {result.get('session_summary', 'N/A')[:100]}...")
        print(f"   Insights: {len(result.get('insights_extracted', []))} extracted")
        
    finally:
        await memory.close()
    
    # Clean up demo file
    if os.path.exists("demo_unified.db"):
        os.remove("demo_unified.db")


async def example_context_manager():
    """Example 2: Using context manager for automatic session management."""
    print("\n" + "=" * 70)
    print("Example 2: Context Manager (Auto Session Management)")
    print("=" * 70)
    
    openai_client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    )
    
    # Context manager automatically starts and ends session
    async with AgentMemory(
        user_id="demo_user_456",
        openai_client=openai_client,
        db_path="demo_context_manager.db"
    ) as memory:
        # Session automatically started
        print(f"\n✅ Session auto-started: {memory.session_id[:8]}...")
        
        await memory.add_turn(
            "What's the difference between traditional and Roth 401k?",
            "The main difference is when you pay taxes: Traditional 401k uses pre-tax dollars and you pay taxes on withdrawals; Roth 401k uses after-tax dollars but withdrawals are tax-free..."
        )
        print("   Added turn about 401k comparison")
        
        context = memory.get_context()
        print(f"   Context length: {len(context)} characters")
        
        # Session automatically ended when exiting context manager
    
    print("✅ Session auto-ended (with reflection)")
    
    # Clean up
    if os.path.exists("demo_context_manager.db"):
        os.remove("demo_context_manager.db")


async def example_factory_function():
    """Example 3: Using factory function for cleaner initialization."""
    print("\n" + "=" * 70)
    print("Example 3: Factory Function")
    print("=" * 70)
    
    openai_client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    )
    
    # Use factory function
    memory = create_agent_memory(
        user_id="demo_user_789",
        db_type=DatabaseType.SQLITE,  # Explicit type
        openai_client=openai_client,
        db_path="demo_factory.db"
    )
    
    async with memory:
        print(f"\n✅ Memory created via factory: {memory.session_id[:8]}...")
        
        await memory.add_turn(
            "Tell me about index funds.",
            "Index funds are a type of mutual fund that tracks a market index like the S&P 500..."
        )
        print("   Added turn about index funds")
        
        status = memory.get_status()
        print(f"   Status: {status['db_type']}, session_started={status['session_started']}")
    
    # Clean up
    if os.path.exists("demo_factory.db"):
        os.remove("demo_factory.db")


async def example_cosmosdb():
    """Example 4: CosmosDB backend (enterprise, requires Azure)."""
    print("\n" + "=" * 70)
    print("Example 4: CosmosDB Backend (Enterprise)")
    print("=" * 70)
    
    # Check for either connection string or endpoint
    connection_string = os.getenv("COSMOS_CONNECTION_STRING")
    cosmos_endpoint = os.getenv("COSMOS_ENDPOINT")
    
    if not connection_string and not cosmos_endpoint:
        print("\n⚠️  COSMOS_CONNECTION_STRING or COSMOS_ENDPOINT not set - skipping CosmosDB example")
        print("   Set one of these environment variables to test CosmosDB backend")
        return
    
    openai_client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    )
    
    # Create config with correct models
    config = AgentMemoryConfig(
        reasoning_model=os.getenv("AZURE_OPENAI_REASONING_MODEL", "gpt-4o"),
        processing_model=os.getenv("AZURE_OPENAI_PROCESSING_MODEL", "gpt-4o-mini"),
        embedding_model=os.getenv("AZURE_OPENAI_EMB_DEPLOYMENT", "text-embedding-ada-002")
    )
    
    # Same API, different backend
    # Will use connection_string if available, otherwise endpoint with AAD auth
    memory = AgentMemory(
        user_id="demo_cosmos_user",
        openai_client=openai_client,
        db_type=DatabaseType.COSMOSDB,  # Switch to CosmosDB
        connection_string=connection_string,  # May be None, will use endpoint
        config=config
    )
    
    try:
        await memory.start_session()
        print(f"\n✅ CosmosDB session started: {memory.session_id[:8]}...")
        
        await memory.add_turn(
            "What are the tax benefits of a 529 plan?",
            "A 529 plan offers several tax benefits: contributions grow tax-free, withdrawals for qualified education expenses are tax-free..."
        )
        print("   Added turn about 529 plans")
        
        context = memory.get_context()
        print(f"   Context: {len(context)} characters")
        
        await memory.end_session()
        print("✅ CosmosDB session ended")
        
    finally:
        await memory.close()


async def example_custom_config():
    """Example 5: Custom configuration."""
    print("\n" + "=" * 70)
    print("Example 5: Custom Configuration")
    print("=" * 70)
    
    openai_client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    )
    
    # Custom configuration
    config = AgentMemoryConfig(
        buffer_size=4,           # Smaller buffer for demo
        active_turns=2,          # Keep 2 recent turns
        top_k_results=3,         # Search results limit
        auto_enrich_context=False,  # Disable auto-enrichment
        trigger_reflection_on_end=True,  # Extract insights on end
        reasoning_model=os.getenv("AZURE_OPENAI_REASONING_MODEL", "gpt-4o"),
        processing_model=os.getenv("AZURE_OPENAI_PROCESSING_MODEL", "gpt-4o-mini"),
    )
    
    memory = AgentMemory(
        user_id="demo_custom_config",
        openai_client=openai_client,
        config=config,
        db_path="demo_custom.db"
    )
    
    async with memory:
        print(f"\n✅ Memory with custom config: buffer={config.buffer_size}, active_turns={config.active_turns}")
        
        # Add multiple turns to see buffer behavior
        for i in range(5):
            await memory.add_turn(
                f"Question {i+1} about investing",
                f"Answer {i+1} with financial advice"
            )
            print(f"   Added turn {i+1}")
        
        context = memory.get_context()
        # With buffer_size=4, older turns should be summarized
        print(f"   Final context length: {len(context)} chars")
    
    # Clean up
    if os.path.exists("demo_custom.db"):
        os.remove("demo_custom.db")


async def main():
    """Run all examples."""
    print("\n" + "🚀 " * 20)
    print("Agent Memory - Unified API Demo")
    print("🚀 " * 20 + "\n")
    
    await example_sqlite()
    await example_context_manager()
    await example_factory_function()
    await example_cosmosdb()
    await example_custom_config()
    
    print("\n" + "=" * 70)
    print("✅ All examples completed!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
