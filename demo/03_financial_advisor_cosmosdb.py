"""
Demo 3: Financial Advisor with CosmosDB Backend
================================================

This demo is identical to 01_financial_advisor.py but uses Azure CosmosDB
instead of SQLite for enterprise-grade, globally distributed storage.

Requirements:
- Azure CosmosDB for NoSQL account with vector search enabled
- Set environment variables:
  - COSMOS_ENDPOINT or AZURE_COSMOS_ENDPOINT
  - COSMOS_CONNECTION_STRING or AZURE_COSMOS_CONNECTION_STRING
  - Or configure DefaultAzureCredential for AAD auth

See infra/README.md for CosmosDB setup instructions.
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from openai import AzureOpenAI
from azure.identity import DefaultAzureCredential
from agent_framework import ChatAgent, tool
from agent_framework.azure import AzureOpenAIChatClient

from memory import AgentMemory, AgentMemoryConfig
from memory.db import DatabaseType

# Demo configuration
USER_ID = "sarah_demo_cosmos"


# Define tools for the financial advisor
@tool(name="get_401k_limit", description="Get 401k contribution limits for a given year")
def get_401k_limit(year: int) -> str:
    """Get 401k contribution limits."""
    limits = {2024: "$23,000 (under 50), $30,500 (50+)", 2025: "$23,500 (under 50), $31,000 (50+)"}
    return limits.get(year, "Information not available for this year")


@tool(name="get_roth_ira_limit", description="Get Roth IRA contribution limits for a given year")
def get_roth_ira_limit(year: int) -> str:
    """Get Roth IRA contribution limits."""
    limits = {2024: "$7,000 (under 50), $8,000 (50+)", 2025: "$7,000 (under 50), $8,000 (50+)"}
    return limits.get(year, "Information not available for this year")


async def run_session(
    agent: ChatAgent,
    memory: AgentMemory,
    session_name: str,
    queries: list[str]
) -> None:
    """Run a conversation session with multiple queries."""
    print(f"\n{'='*70}")
    print(f"SESSION: {session_name}")
    print(f"{'='*70}")
    
    # Start new session
    await memory.start_session()
    print(f"Session ID: {memory.session_id[:8]}...")
    
    # Show memory context
    context = memory.get_context()
    print(f"\n📚 Memory context loaded ({len(context)} chars):")
    print(f"   {context[:200]}..." if len(context) > 200 else f"   {context}")
    print()
    
    # Process each query
    for query in queries:
        print(f"\n👤 User: {query}")
        response = await agent.run(query)
        print(f"🤖 Advisor: {response.text[:300]}..." if len(response.text) > 300 else f"🤖 Advisor: {response.text}")
    
    # End session (triggers reflection and long-term synthesis)
    result = await memory.end_session(trigger_reflection=True)
    print(f"\n✅ Session complete")
    print(f"   Summary: {result.get('summary', '')[:80]}...")
    print(f"   Insights: {len(result.get('insights', []))}")


async def main():
    """Run the financial advisor demo with CosmosDB backend."""
    print("=" * 70)
    print("🧠 Agent Memory Demo: Financial Advisor (CosmosDB)")
    print("   Integration: Agent Framework ContextProvider")
    print("   Memory: Automatic (no manual add_turn calls)")
    print("   Backend: Azure CosmosDB (enterprise-grade)")
    print("=" * 70)
    
    # Check CosmosDB credentials
    cosmos_endpoint = os.getenv("COSMOS_ENDPOINT") or os.getenv("AZURE_COSMOS_ENDPOINT")
    cosmos_conn = os.getenv("COSMOS_CONNECTION_STRING") or os.getenv("AZURE_COSMOS_CONNECTION_STRING")
    
    if not cosmos_endpoint and not cosmos_conn:
        print("\n❌ CosmosDB credentials not found!")
        print("   Set COSMOS_ENDPOINT or COSMOS_CONNECTION_STRING environment variable")
        print("   See infra/README.md for CosmosDB setup instructions")
        return
    
    print(f"\n✅ CosmosDB: {'Endpoint' if cosmos_endpoint else 'Connection String'} configured")
    
    # Azure OpenAI client for embeddings
    openai_client = AzureOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    )
    
    # Memory configuration with CosmosDB backend
    config = AgentMemoryConfig(
        auto_enrich_context=True,
        enrichment_trigger_keywords=[
            "remember", "recall", "previous", "last time", "before",
            "discussed", "mentioned", "told you", "my profile"
        ],
        include_longterm_insights=True,
        include_recent_sessions=True,
        include_cumulative_summary=True,
        include_active_turns=False,
        longterm_synthesis_frequency=1,
        inject_recall_tool=False,
        auto_manage_sessions=False,
        # CosmosDB specific
        database_name=os.getenv("COSMOS_DATABASE_NAME", "agent_memory_db"),
    )
    
    # Create Agent Memory with CosmosDB backend
    memory = AgentMemory(
        user_id=USER_ID,
        openai_client=openai_client,
        db_type=DatabaseType.COSMOSDB,  # Use CosmosDB instead of SQLite
        connection_string=cosmos_conn,  # Or will use COSMOS_ENDPOINT env var
        config=config,
    )
    
    # Create Agent Framework chat client
    credential = DefaultAzureCredential()
    chat_client = AzureOpenAIChatClient(
        credential=credential,
        endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        deployment_name=os.getenv("AZURE_OPENAI_REASONING_MODEL", "gpt-4o")
    )
    
    # Create the agent with memory as context_provider
    agent = ChatAgent(
        chat_client=chat_client,
        instructions="""You are an expert financial advisor specializing in retirement planning.

Your approach:
- Provide personalized advice based on client's profile
- Reference details from previous conversations when relevant
- Explain complex concepts clearly
- Be proactive about suggesting strategies

Always be professional, accurate, and personalized.""",
        tools=[get_401k_limit, get_roth_ira_limit],
        context_provider=memory,
    )
    
    try:
        # SESSION 1: Initial Consultation
        await run_session(
            agent=agent,
            memory=memory,
            session_name="Initial Consultation",
            queries=[
                "Hi! I'm Sarah, 35 years old, software engineer making $150,000/year.",
                "I'm comfortable with moderate-to-high risk since I have 30 years until retirement.",
                "My employer offers a 401k with 4% match. What's the best strategy?"
            ]
        )
        
        # SESSION 2: Investment Strategy (new session - tests memory recall)
        await run_session(
            agent=agent,
            memory=memory,
            session_name="Investment Strategy",
            queries=[
                "Based on what we discussed before, what asset allocation do you recommend?",
                "Should I include international stocks given my risk tolerance?"
            ]
        )
        
        # SESSION 3: Tax Planning
        await run_session(
            agent=agent,
            memory=memory,
            session_name="Tax Planning",
            queries=[
                "Given my income and the retirement accounts we discussed, how can I optimize taxes?",
                "Should I consider Roth conversions based on my profile?"
            ]
        )
        
        # Show final memory state
        print(f"\n{'='*70}")
        print("📊 FINAL MEMORY STATE")
        print(f"{'='*70}")
        
        # Search memory
        facts = await memory.search("What is Sarah's risk tolerance?")
        print(f"\n🔍 Searching: 'What is Sarah's risk tolerance?'")
        print(f"   Result: {facts[:100]}..." if len(facts) > 100 else f"   Result: {facts}")
        
        # Get insights
        insights = await memory.get_insights(limit=10)
        print(f"\n💡 Extracted Insights: {len(insights)}")
        for insight in insights[:3]:
            text = insight.get('insight_text', insight.get('content', ''))[:70]
            print(f"   • {text}...")
        
        # Get sessions
        sessions = await memory.get_sessions(limit=5)
        print(f"\n📅 Sessions: {len(sessions)}")
        for session in sessions[:3]:
            summary = session.get('summary', '')[:50]
            print(f"   • {summary}...")
        
    finally:
        await memory.close()
    
    print(f"\n{'='*70}")
    print("✅ Demo Complete!")
    print("   Data persisted to CosmosDB for future sessions")
    print(f"{'='*70}")


if __name__ == "__main__":
    asyncio.run(main())
