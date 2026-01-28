"""
Financial Advisor Demo - Unified API
=====================================

This demo showcases a multi-session financial advisor using the unified 
AgentMemory API. The same code works with SQLite or CosmosDB backends.

Scenario:
- Session 1: User discusses retirement planning, reveals risk profile
- Session 2: (New session) User asks about investments - agent uses memory
- Session 3: (New session) Tax strategies - agent recalls all previous context

Run: python demos/scenarios/financial_advisor_unified.py
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

from azure.identity import AzureCliCredential
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from openai import AzureOpenAI

from memory import AgentMemory, AgentMemoryConfig
from memory.db.factory import DatabaseType


# ============================================================================
# Agent Tools
# ============================================================================

def get_401k_contribution_limit(year: int) -> str:
    """Tool: Get 401k contribution limits for a given year."""
    limits = {
        2024: "$23,000 (under 50), $30,500 (50+)",
        2025: "$23,500 (under 50), $31,000 (50+)"
    }
    return limits.get(year, "Information not available for this year")


def get_roth_ira_limit(year: int) -> str:
    """Tool: Get Roth IRA contribution limits."""
    limits = {
        2024: "$7,000 (under 50), $8,000 (50+)",
        2025: "$7,000 (under 50), $8,000 (50+)"
    }
    return limits.get(year, "Information not available for this year")


def calculate_retirement_needs(current_age: int, retirement_age: int, annual_expenses: int) -> str:
    """Tool: Calculate estimated retirement savings needed."""
    years_in_retirement = 90 - retirement_age  # Assume living to 90
    total_needed = annual_expenses * years_in_retirement
    return f"Estimated retirement savings needed: ${total_needed:,} (assuming annual expenses of ${annual_expenses:,} for {years_in_retirement} years)"


# ============================================================================
# Main Demo
# ============================================================================

async def run_session(
    memory: AgentMemory,
    agent: ChatAgent,
    queries: list[str],
    session_name: str
) -> None:
    """Run a single conversation session."""
    
    # Start a new session
    await memory.start_session()
    print(f"   Session ID: {memory.session_id[:8]}...")
    
    # Get memory context for the agent
    memory_context = memory.get_context()
    if memory_context:
        print(f"   Loaded memory context: {len(memory_context)} characters")
    
    # Get a new thread for this session
    thread = agent.get_new_thread()
    
    # Inject memory context into thread if available
    if memory_context:
        thread.add_message(
            role="user",
            content=f"[MEMORY CONTEXT]\n{memory_context}\n[END MEMORY CONTEXT]\n\nPlease acknowledge you have loaded my previous context."
        )
        response = await agent.run(thread=thread)
        print(f"\n   Agent (memory loaded): {response.text[:100]}...")
    
    # Process each user query
    for i, query in enumerate(queries, 1):
        print(f"\n   User ({i}): {query}")
        
        # Add user message to thread
        thread.add_message(role="user", content=query)
        
        # Get agent response
        response = await agent.run(thread=thread)
        print(f"   Agent: {response.text[:200]}...")
        
        # Store in memory
        await memory.add_turn(query, response.text)
    
    # End session with reflection
    result = await memory.end_session()
    print(f"\n   ✅ Session complete")
    print(f"      Summary: {result.get('session_summary', 'N/A')[:80]}...")
    print(f"      Insights extracted: {len(result.get('insights_extracted', []))}")


async def main():
    """Run the financial advisor demo."""
    print("=" * 80)
    print("Financial Advisor Demo - Unified Agent Memory API")
    print("=" * 80)
    print()
    
    # Configuration
    user_id = "financial_demo_user"
    
    # Choose your backend:
    # - DatabaseType.SQLITE (default, no server required)
    # - DatabaseType.COSMOSDB (enterprise, requires Azure)
    
    use_cosmosdb = os.getenv("COSMOS_CONNECTION_STRING") is not None
    db_type = DatabaseType.COSMOSDB if use_cosmosdb else DatabaseType.SQLITE
    db_path = f"demo_financial_{user_id}.db"
    
    print(f"User ID: {user_id}")
    print(f"Backend: {db_type.value}")
    if db_type == DatabaseType.SQLITE:
        print(f"Database: {db_path}")
    print()
    
    # Clean up previous demo data (for SQLite)
    if db_type == DatabaseType.SQLITE and os.path.exists(db_path):
        os.remove(db_path)
    
    # Create OpenAI client for embeddings and memory processing
    openai_client = AzureOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    )
    
    # Memory configuration
    config = AgentMemoryConfig(
        buffer_size=6,
        active_turns=4,
        reasoning_model=os.getenv("AZURE_OPENAI_REASONING_MODEL", "gpt-4o"),
        processing_model=os.getenv("AZURE_OPENAI_PROCESSING_MODEL", "gpt-4o-mini"),
    )
    
    # Create unified memory - works with any backend!
    memory_kwargs = {
        "user_id": user_id,
        "openai_client": openai_client,
        "config": config,
        "db_type": db_type,
    }
    
    if db_type == DatabaseType.SQLITE:
        memory_kwargs["db_path"] = db_path
    else:
        memory_kwargs["connection_string"] = os.getenv("COSMOS_CONNECTION_STRING")
    
    memory = AgentMemory(**memory_kwargs)
    
    # Create agent
    credential = AzureCliCredential()
    chat_client = AzureOpenAIChatClient(
        credential=credential,
        endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        model=os.getenv("AZURE_OPENAI_REASONING_MODEL", "gpt-4o")
    )
    
    agent = ChatAgent(
        chat_client=chat_client,
        instructions="""You are an expert financial advisor specializing in retirement planning.
        
Key responsibilities:
- Provide personalized retirement planning advice
- Explain complex financial concepts clearly
- Remember client details across sessions
- Make recommendations based on client's risk profile and goals

Always be professional, accurate, and personalized in your advice.""",
        tools=[
            get_401k_contribution_limit,
            get_roth_ira_limit,
            calculate_retirement_needs
        ]
    )
    
    try:
        # =====================================================================
        # SESSION 1: Initial Consultation - Build User Profile
        # =====================================================================
        print("-" * 80)
        print("SESSION 1: Initial Retirement Planning Consultation")
        print("-" * 80)
        
        await run_session(
            memory=memory,
            agent=agent,
            session_name="Initial Consultation",
            queries=[
                "Hi! I'm Sarah, 35 years old, and I want to start planning for retirement. I'm a software engineer making $150,000 annually.",
                "I'm fairly comfortable with risk since I have a long time horizon. What retirement accounts should I prioritize?",
                "My employer offers a 401k with 4% match. Should I max that out first?"
            ]
        )
        
        # =====================================================================
        # SESSION 2: Investment Strategy - Agent Should Remember User Profile
        # =====================================================================
        print("\n" + "-" * 80)
        print("SESSION 2: Investment Strategy Discussion")
        print("-" * 80)
        
        await run_session(
            memory=memory,
            agent=agent,
            session_name="Investment Strategy",
            queries=[
                "I've been thinking about what we discussed. What's a good asset allocation for my situation?",
                "Should I consider international stocks given my risk tolerance?",
                "How often should I rebalance my portfolio?"
            ]
        )
        
        # =====================================================================
        # SESSION 3: Tax Optimization - Agent Recalls All Previous Context
        # =====================================================================
        print("\n" + "-" * 80)
        print("SESSION 3: Tax Optimization Strategies")
        print("-" * 80)
        
        await run_session(
            memory=memory,
            agent=agent,
            session_name="Tax Optimization",
            queries=[
                "Given everything we've discussed about my retirement accounts, how can I optimize my tax situation?",
                "Should I do Roth conversions? What's the strategy there?",
                "Any other tax-advantaged accounts I should consider with my income level?"
            ]
        )
        
        # =====================================================================
        # Display Final Memory State
        # =====================================================================
        print("\n" + "=" * 80)
        print("MEMORY SUMMARY")
        print("=" * 80)
        
        # Get insights
        insights = await memory.get_insights()
        print(f"\n📊 Total insights stored: {len(insights)}")
        for insight in insights[:5]:
            category = insight.get("category", "general")
            text = insight.get("insight_text", "")[:80]
            print(f"   [{category}] {text}...")
        
        # Get sessions
        sessions = await memory.get_sessions()
        print(f"\n📅 Total sessions: {len(sessions)}")
        for session in sessions:
            summary = session.get("summary", "")[:60]
            print(f"   - {summary}...")
        
        # Search memory
        print("\n🔍 Memory Search: 'What is Sarah's risk tolerance?'")
        search_result = await memory.search("What is Sarah's risk tolerance?")
        print(f"   {search_result[:200]}...")
        
    finally:
        await memory.close()
        
        # Clean up demo database (SQLite only)
        if db_type == DatabaseType.SQLITE and os.path.exists(db_path):
            os.remove(db_path)
            print(f"\n🧹 Cleaned up demo database: {db_path}")
    
    print("\n" + "=" * 80)
    print("✅ Demo Complete!")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())
