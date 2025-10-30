"""
Example usage of the simplified CosmosAgentMemory interface.

This demonstrates the streamlined API for agent memory.
"""

import asyncio
import os
from openai import AzureOpenAI
from memory import CosmosAgentMemory, MemoryConfig


async def example_simple_usage():
    """Example 1: Simple usage with connection string."""
    print("=" * 70)
    print("Example 1: Simple Usage")
    print("=" * 70)
    
    # Create OpenAI client
    openai_client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version="2024-02-15-preview"
    )
    
    # Initialize memory with just connection string
    memory = CosmosAgentMemory(
        user_id="user_123",
        cosmos_connection_string=os.getenv("COSMOS_CONNECTION_STRING"),
        openai_client=openai_client
    )
    
    # Start session
    await memory.start_session()
    
    # Add conversation turns
    await memory.add_turn(
        "Hello! I'm interested in retirement planning.",
        "Great! I'd be happy to help you with retirement planning. What specific aspects are you interested in?"
    )
    
    await memory.add_turn(
        "I want to understand Roth IRA options.",
        "A Roth IRA is an excellent retirement savings vehicle. Contributions are made with after-tax dollars, but qualified withdrawals are tax-free..."
    )
    
    # Get memory context (for adding to AI prompt)
    context = memory.get_context()
    print(f"\nMemory Context:\n{context[:200]}...")
    
    # Search memory
    facts = await memory.search("What did the user ask about?")
    print(f"\nSearch Result: {facts}")
    
    # End session (extracts summary and insights)
    summary = await memory.end_session()
    print(f"\nSession Summary: {summary.get('session_summary', 'N/A')}")
    print(f"Insights Extracted: {len(summary.get('insights_extracted', []))}")


async def example_context_manager():
    """Example 2: Using context manager for automatic session management."""
    print("\n" + "=" * 70)
    print("Example 2: Context Manager Usage")
    print("=" * 70)
    
    openai_client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version="2024-02-15-preview"
    )
    
    # Context manager automatically starts and ends session
    async with CosmosAgentMemory(
        user_id="user_456",
        cosmos_connection_string=os.getenv("COSMOS_CONNECTION_STRING"),
        openai_client=openai_client
    ) as memory:
        # Session automatically started
        
        await memory.add_turn(
            "What's the difference between traditional and Roth IRA?",
            "The main difference is when you pay taxes..."
        )
        
        context = memory.get_context()
        print(f"\nContext available: {len(context)} characters")
        
        # Session automatically ended on exit with reflection


async def example_custom_config():
    """Example 3: Using custom configuration."""
    print("\n" + "=" * 70)
    print("Example 3: Custom Configuration")
    print("=" * 70)
    
    # Custom memory configuration
    config = MemoryConfig(
        buffer_size=15,  # Larger buffer before summarization
        active_turns=7,   # More recent turns in context
        database_name="financial_advisor_memory",
        trigger_reflection_on_end=True,  # Always extract insights
        insight_categories=[
            "demographics",
            "financial_goals",
            "risk_profile",
            "investment_preferences"
        ]
    )
    
    openai_client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version="2024-02-15-preview"
    )
    
    memory = CosmosAgentMemory(
        user_id="user_789",
        cosmos_connection_string=os.getenv("COSMOS_CONNECTION_STRING"),
        openai_client=openai_client,
        config=config
    )
    
    await memory.start_session()
    
    # ... conversation ...
    
    # Query insights
    insights = await memory.get_insights(category="financial_goals", limit=5)
    print(f"\nInsights found: {len(insights)}")
    
    # Query sessions
    sessions = await memory.get_sessions(limit=5)
    print(f"Recent sessions: {len(sessions)}")
    
    await memory.end_session()


async def example_explicit_session_control():
    """Example 4: Explicit session ID control."""
    print("\n" + "=" * 70)
    print("Example 4: Explicit Session Control")
    print("=" * 70)
    
    openai_client = AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_version="2024-02-15-preview"
    )
    
    memory = CosmosAgentMemory(
        user_id="user_101",
        cosmos_connection_string=os.getenv("COSMOS_CONNECTION_STRING"),
        openai_client=openai_client,
        auto_start_session=False  # Manual control
    )
    
    # Start first session with specific ID
    await memory.start_session(session_id="morning_consultation_2024_10_29")
    await memory.add_turn("Hello", "Good morning!")
    await memory.end_session()
    
    # Start second session
    await memory.start_session(session_id="afternoon_followup_2024_10_29")
    await memory.add_turn("Let's continue", "Sure, let's pick up where we left off")
    
    # The memory system remembers context from previous sessions
    context = memory.get_context()
    print(f"\nContext includes previous session information: {len(context)} chars")
    
    await memory.end_session()


async def main():
    """Run all examples."""
    print("\n" + "=" * 70)
    print("CosmosAgentMemory Usage Examples")
    print("=" * 70)
    print()
    print("NOTE: These examples require valid Azure credentials.")
    print("Set COSMOS_CONNECTION_STRING, AZURE_OPENAI_API_KEY, and")
    print("AZURE_OPENAI_ENDPOINT environment variables to run.")
    print()
    
    # Check if credentials are available
    if not all([
        os.getenv("COSMOS_CONNECTION_STRING"),
        os.getenv("AZURE_OPENAI_API_KEY"),
        os.getenv("AZURE_OPENAI_ENDPOINT")
    ]):
        print("⚠️  Missing credentials - skipping live examples")
        print()
        print("To run these examples, set:")
        print("  - COSMOS_CONNECTION_STRING")
        print("  - AZURE_OPENAI_API_KEY")
        print("  - AZURE_OPENAI_ENDPOINT")
        return
    
    # Run examples
    await example_simple_usage()
    await example_context_manager()
    await example_custom_config()
    await example_explicit_session_control()
    
    print("\n" + "=" * 70)
    print("All examples completed!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
