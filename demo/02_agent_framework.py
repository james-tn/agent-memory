"""
Financial Advisor Demo - Agent Framework Integration
=====================================================

This demo showcases how AgentMemory integrates with Microsoft Agent Framework
as a ContextProvider, enabling **automatic** memory management.

Key Features Demonstrated:
- AgentMemory as a `context_provider` - no manual memory calls needed
- Automatic context injection via `invoking()` hook
- Automatic turn capture via `invoked()` hook  
- Auto-enrichment: keyword-triggered memory search
- Hidden recall_facts tool injection (optional)
- Granular context control (insights, sessions, summary, turns)
- SQLite backend for zero-configuration local development

How it works:
1. Memory is passed to ChatAgent as `context_providers=[memory]`
2. Before each turn: `invoking()` injects memory context into the prompt
3. After each turn: `invoked()` automatically stores the conversation
4. At session end: Reflection extracts insights for future sessions

Run: uv run python -m demos.01_financial_advisor
"""

import asyncio
import os
import sys
from pathlib import Path

# Setup paths
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from dotenv import load_dotenv
load_dotenv(BASE_DIR / '.env')

from azure.identity import DefaultAzureCredential
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient
from openai import AzureOpenAI

from memory import AgentMemory, AgentMemoryConfig


# ============================================================================
# Configuration
# ============================================================================

USER_ID = "sarah_demo"
DB_PATH = "demo_financial_advisor.db"


# ============================================================================
# Agent Tools
# ============================================================================

def get_401k_limit(year: int = 2025) -> str:
    """Get 401k contribution limits for a given year."""
    limits = {2024: "$23,000 (under 50), $30,500 (50+)", 2025: "$23,500 (under 50), $31,000 (50+)"}
    return limits.get(year, "Information not available")


def get_roth_ira_limit(year: int = 2025) -> str:
    """Get Roth IRA contribution limits."""
    return "$7,000 (under 50), $8,000 (50+)"


# ============================================================================
# Demo
# ============================================================================

async def run_session(agent: ChatAgent, memory: AgentMemory, queries: list[str], session_name: str):
    """
    Run a conversation session.
    
    Note: Memory is automatically managed via the ContextProvider interface.
    - invoking() injects context before each agent call
    - invoked() stores each turn after the agent responds
    """
    print(f"\n{'='*70}")
    print(f"SESSION: {session_name}")
    print(f"{'='*70}")
    
    # Start a new session
    await memory.start_session()
    print(f"Session ID: {memory.session_id[:8]}...")
    
    # Show loaded memory context
    context = memory.get_context()
    if context.strip():
        print(f"\n📚 Memory context loaded ({len(context)} chars):")
        preview = context[:300] + "..." if len(context) > 300 else context
        for line in preview.split('\n')[:6]:
            print(f"   {line}")
    else:
        print("\n📚 No previous memory (first session)")
    
    # Process queries - memory is automatically managed!
    for query in queries:
        print(f"\n👤 User: {query}")
        
        # Just call agent.run() - memory injection and storage happen automatically
        # via the context_providers=[memory] integration
        response = await agent.run(query)
        
        print(f"🤖 Advisor: {response.text[:250]}...")
    
    # End session - triggers reflection and insight extraction
    result = await memory.end_session()
    print(f"\n✅ Session complete")
    print(f"   Summary: {result.get('session_summary', 'N/A')[:100]}...")
    print(f"   Insights: {len(result.get('insights_extracted', []))}")


async def main():
    """Run the financial advisor demo with automatic memory management."""
    print("=" * 70)
    print("🧠 Agent Memory Demo: Financial Advisor")
    print("   Integration: Agent Framework ContextProvider")
    print("   Memory: Automatic (no manual add_turn calls)")
    print("   Backend: SQLite (zero-config)")
    print("=" * 70)
    
    # Clean up previous demo
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print("🧹 Cleaned up previous demo database")
    
    # =========================================================================
    # Setup
    # =========================================================================
    
    # Azure OpenAI client for embeddings
    openai_client = AzureOpenAI(
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-08-01-preview")
    )
    
    # Memory configuration with auto-enrichment and granular control
    config = AgentMemoryConfig(
        # Auto-enrichment: LLM-based semantic detection (more natural than keywords)
        auto_enrich_context=True,
        enrichment_mode="llm",  # "llm" (semantic, human-like) or "keyword" (simple, fast)
        # Fallback keywords (used when enrichment_mode="keyword")
        enrichment_trigger_keywords=[
            "remember", "recall", "previous", "last time", "before",
            "discussed", "mentioned", "told you", "my profile",
            "based on", "given my", "considering my"
        ],
        
        # Granular context control - what to inject
        include_longterm_insights=True,   # Include user insights
        include_recent_sessions=True,     # Include past session summaries
        include_cumulative_summary=True,  # Include current session summary
        include_active_turns=False,       # Don't duplicate recent turns (agent has them)
        
        # Long-term synthesis - create user profile after every session
        longterm_synthesis_frequency=1,   # Synthesize after every session (was 5)
        
        # Hidden tool injection - agent can search memory autonomously
        inject_recall_tool=False,  # Set to True to enable hidden recall_facts tool
        
        # Session management
        auto_manage_sessions=False,  # We'll manage sessions explicitly for demo
    )
    
    # Create Agent Memory - this will be our context_provider
    memory = AgentMemory(
        user_id=USER_ID,
        openai_client=openai_client,
        db_path=DB_PATH,
        config=config,
    )
    
    # Create Agent Framework chat client
    credential = DefaultAzureCredential()
    chat_client = AzureOpenAIChatClient(
        credential=credential,
        endpoint=os.getenv("AZURE_OPENAI_ENDPOINT"),
        deployment_name=os.getenv("AZURE_OPENAI_REASONING_MODEL", "gpt-4o")
    )
    
    # Create the agent with memory as a context_provider
    # This is the key integration - memory automatically:
    # 1. Injects context before each turn (via invoking())
    # 2. Stores each turn after response (via invoked())
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
        context_provider=memory,  # ← Automatic memory integration!
    )
    
    try:
        # =====================================================================
        # SESSION 1: Initial Consultation - Build User Profile
        # =====================================================================
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
        
        # =====================================================================
        # SESSION 2: Investment Strategy - Agent Automatically Recalls Profile
        # =====================================================================
        await run_session(
            agent=agent,
            memory=memory,
            session_name="Investment Strategy",
            queries=[
                "Based on what we discussed before, what asset allocation do you recommend?",
                "Should I include international stocks given my risk tolerance?",
            ]
        )
        
        # =====================================================================
        # SESSION 3: Tax Planning - Agent Uses All Accumulated Context
        # =====================================================================
        await run_session(
            agent=agent,
            memory=memory,
            session_name="Tax Planning",
            queries=[
                "Given my income and the retirement accounts we discussed, how can I optimize taxes?",
                "Should I consider Roth conversions based on my profile?",
            ]
        )
        
        # =====================================================================
        # Show Final Memory State
        # =====================================================================
        print(f"\n{'='*70}")
        print("📊 FINAL MEMORY STATE")
        print(f"{'='*70}")
        
        # Demonstrate memory search
        print("\n🔍 Searching: 'What is Sarah's risk tolerance?'")
        result = await memory.search("What is Sarah's risk tolerance?")
        print(f"   Result: {result[:200]}...")
        
        # Show insights
        await memory.start_session()
        insights = await memory.get_insights()
        print(f"\n💡 Extracted Insights: {len(insights)}")
        for insight in insights[:3]:
            print(f"   • {insight.get('insight_text', '')[:80]}...")
        
        # Show sessions
        sessions = await memory.get_sessions()
        print(f"\n📅 Sessions: {len(sessions)}")
        for s in sessions:
            print(f"   • {s.get('summary', '')[:60]}...")
        
        await memory.end_session()
        
    finally:
        await memory.close()
        
        # Clean up demo database (with retry for Windows file locks)
        import time
        for _ in range(3):
            try:
                if os.path.exists(DB_PATH):
                    os.remove(DB_PATH)
                    print(f"\n🧹 Cleaned up: {DB_PATH}")
                break
            except PermissionError:
                time.sleep(0.5)
    
    print(f"\n{'='*70}")
    print("✅ Demo Complete!")
    print("   Memory was automatically managed via context_providers")
    print(f"{'='*70}")


if __name__ == "__main__":
    asyncio.run(main())
