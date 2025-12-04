"""
Demo 1 (Remote): Financial Advisor with Remote Memory Service
==============================================================

This demo showcases the same functionality as demo1_financial_advisor.py,
but using the remote memory service via RemoteMemoryProvider.

Key differences from embedded version:
- No CosmosDB/OpenAI clients in client code
- Much simpler setup (just service URL and user_id)
- Memory service handles all state management
- 0ms session restoration for hot sessions

Scenario:
- Session 1: User discusses retirement planning, reveals risk profile
- Session 2: (New thread) User asks about investments - agent remembers profile  
- Session 3: (New thread) Tax strategies - agent recalls all previous context
"""

import asyncio
import uuid
import os
import requests
from azure.identity import AzureCliCredential
from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient

from memory.cosmos_memory_provider import CosmosMemoryProvider


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


def wait_for_session_end(memory_service_url: str, session_id: str, timeout: int = 60) -> bool:
    """
    Poll the session status endpoint until background processing completes.
    
    Args:
        memory_service_url: Base URL of memory service
        session_id: Session ID to check
        timeout: Maximum seconds to wait
    
    Returns:
        True if completed successfully, False if timeout or error
    """
    import time
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{memory_service_url}/sessions/status", params={"session_id": session_id})
            if response.status_code == 200:
                status_data = response.json()
                status = status_data.get("status")
                
                if status == "complete":
                    print(f"   ✓ Background processing complete (insights: {status_data.get('insights_count', 0)})")
                    return True
                elif status == "error":
                    print(f"   ⚠️  Background processing error: {status_data.get('error')}")
                    return False
                elif status == "processing":
                    print("   ⏳ Background synthesis in progress...", end="\r")
                    time.sleep(2)
                else:
                    # not_found - session might have completed already
                    return True
        except Exception as e:
            print(f"   ⚠️  Error checking status: {e}")
            return False
    
    print(f"   ⚠️  Timeout waiting for background processing")
    return False


def display_longterm_insights(memory_service_url: str, user_id: str) -> None:
    """Fetch and display long-term insights for the user."""
    try:
        response = requests.get(f"{memory_service_url}/memory/insights", params={"user_id": user_id})
        if response.status_code == 200:
            insights = response.json()
            # Filter for long-term insights (note: uses "long_term" with underscore)
            longterm_insights = [i for i in insights if i.get("insight_type") == "long_term"]
            
            if longterm_insights:
                print("🎯 Long-Term User Profile:")
                print("─" * 80)
                for insight in longterm_insights:
                    content = insight.get("content", "")
                    # Display formatted sections
                    lines = content.split("\n")
                    for line in lines:
                        if line.strip():
                            print(f"   {line}")
                print("─" * 80)
                print()
            else:
                print("ℹ️  Long-term profile not yet synthesized (synthesis occurs every N sessions)")
                print()
        else:
            print(f"⚠️  Could not fetch insights: {response.status_code}")
            print()
    except Exception as e:
        print(f"⚠️  Error fetching insights: {e}")
        print()


async def main() -> None:
    print("=" * 80)
    print("Demo 1 (Remote): Financial Advisor with Remote Memory Service")
    print("=" * 80)
    print()
    
    # Setup 
    user_id = f"client_{uuid.uuid4().hex[:8]}"
    user_id = "user1"

    memory_service_url = os.getenv("MEMORY_SERVICE_URL", "http://localhost:8000")
    
    print(f"Client ID: {user_id}")
    print(f"Memory Service: {memory_service_url}")
    print()
    
    # =========================================================================
    # SESSION 1: Initial Consultation - Build User Profile
    # =========================================================================
    print("─" * 80)
    print("SESSION 1: Initial Retirement Planning Consultation")
    print("─" * 80)
    print()
    
    # Create remote memory provider - session auto-starts on first use
    memory_provider = CosmosMemoryProvider(
        service_url=memory_service_url,
        user_id=user_id,
        auto_manage_session=True  # Session starts automatically on first agent.run()
    )
    
    # Note: Session will start automatically on first agent.run()
    # You still must call end_session() explicitly when done
    
    # Create the agent with remote memory provider
    agent = ChatAgent(
        chat_client=AzureOpenAIChatClient(credential=AzureCliCredential(), deployment_name=os.getenv("AZURE_OPENAI_REASONING_MODEL")),
        instructions=(
            "You are a knowledgeable financial advisor specializing in retirement planning. "
            "You provide personalized advice based on each client's unique situation, risk tolerance, "
            "and financial goals. Always remember important details about your clients for future sessions. "
            "Be professional, empathetic, and clear in your explanations."
        ),
        tools=[get_401k_contribution_limit, get_roth_ira_limit, calculate_retirement_needs],
        context_providers=[memory_provider],
    )
    
    # Create thread
    thread = agent.get_new_thread()
    
    # Question 1: Introduce yourself
    query = "Hi, I'm 35 years old and want to start planning for retirement. I currently have $50,000 in savings."
    print(f"👤 Client: {query}")
    result = await agent.run(query, thread=thread)
    print(f"💼 Advisor: {result.text[:500]}...")
    print()
    
    # Question 2: Reveal risk tolerance
    query = "I'm generally conservative with money - I don't like taking big risks. I've never invested in stocks before."
    print(f"👤 Client: {query}")
    result = await agent.run(query, thread=thread)
    print(f"💼 Advisor: {result.text[:500]}...")
    print()
    
    # Question 3: Discuss goals
    query = "I'd like to retire at 65 and maintain my current lifestyle which costs about $60,000 per year."
    print(f"👤 Client: {query}")
    result = await agent.run(query, thread=thread)
    print(f"💼 Advisor: {result.text[:500]}...")
    print()
    
    # Question 4: Current retirement accounts
    query = "I have a 401k through work but I'm only contributing 3%. My employer matches up to 5%."
    print(f"👤 Client: {query}")
    result = await agent.run(query, thread=thread)
    print(f"💼 Advisor: {result.text[:500]}...")
    print()
    
    # Wait for all invoked() callbacks to complete storing turns
    await asyncio.sleep(0.5)
    
    # Explicitly end session - triggers summarization and reflection on server
    # Note: This is REQUIRED - cannot rely on context manager __aexit__
    session_id = memory_provider.session_id  # Capture before closing
    await memory_provider.end_session()
    await memory_provider.close()
    
    print("✅ Session 1 complete - Agent should have learned:")
    print("   - Age: 35, wants to retire at 65")
    print("   - Conservative risk tolerance")
    print("   - Current savings: $50k")
    print("   - Goal: $60k/year in retirement")
    print("   - Underutilizing 401k match")
    print()
    
    # Wait for background synthesis to complete
    print("⏳ Waiting for background synthesis...")
    wait_for_session_end(memory_service_url, session_id)
    print()
    
    # Display long-term insights
    display_longterm_insights(memory_service_url, user_id)
    
    # Small delay to simulate time between sessions
    await asyncio.sleep(2)
    
    # =========================================================================
    # SESSION 2: Follow-up - Investment Advice (NEW THREAD, SAME USER)
    # =========================================================================
    print("─" * 80)
    print("SESSION 2: Investment Strategy Discussion (2 weeks later)")
    print("─" * 80)
    print()
    
    # Create NEW memory provider with SAME user_id
    # Service will restore session context automatically
    memory_provider = CosmosMemoryProvider(
        service_url=memory_service_url,
        user_id=user_id,  # Same user
        auto_manage_session=True  # Session starts automatically on first agent.run()
    )
    
    # Note: Session will start automatically on first agent.run()
    # You still must call end_session() explicitly when done
    
    # Create agent again (could be different instance, e.g., after server restart)
    agent = ChatAgent(
        chat_client=AzureOpenAIChatClient(credential=AzureCliCredential(), deployment_name=os.getenv("AZURE_OPENAI_REASONING_MODEL")),
        instructions=(
            "You are a knowledgeable financial advisor specializing in retirement planning. "
            "You provide personalized advice based on each client's unique situation, risk tolerance, "
            "and financial goals. Always remember important details about your clients for future sessions. "
            "Be professional, empathetic, and clear in your explanations."
        ),
        tools=[get_401k_contribution_limit, get_roth_ira_limit, calculate_retirement_needs],
        context_providers=[memory_provider],
    )
    
    # New thread
    thread = agent.get_new_thread()
    
    # Question 1: Ask about investments WITHOUT repeating profile
    query = "I've been thinking about your advice. What specific investments would you recommend for me?"
    print(f"👤 Client: {query}")
    print("   [NOTE: New thread - testing if agent remembers conservative risk tolerance]")
    result = await agent.run(query, thread=thread)
    print(f"💼 Advisor: {result.text[:250]}...")
    print()
    
    # Question 2: Ask about Roth IRA
    query = "Should I open a Roth IRA? What's the contribution limit for 2025?"
    print(f"👤 Client: {query}")
    result = await agent.run(query, thread=thread)
    print(f"💼 Advisor: {result.text[:500]}...")
    print()
    
    # Wait for all invoked() callbacks to complete
    await asyncio.sleep(0.5)
    
    # Explicitly end session - triggers summarization and reflection on server
    # Note: This is REQUIRED - cannot rely on context manager __aexit__
    session_id = memory_provider.session_id  # Capture before closing
    await memory_provider.end_session()
    await memory_provider.close()
    
    print("✅ Session 2 complete - Testing if agent:")
    print("   - Remembered conservative risk profile")
    print("   - Tailored recommendations accordingly")
    print("   - Didn't ask for information already known")
    print()
    
    # Wait for background synthesis to complete
    print("⏳ Waiting for background synthesis...")
    wait_for_session_end(memory_service_url, session_id)
    print()
    
    # Display long-term insights (may be synthesized now depending on frequency config)
    display_longterm_insights(memory_service_url, user_id)
    
    await asyncio.sleep(2)
    
    # =========================================================================
    # SESSION 3: Tax Strategy (NEW THREAD AGAIN)
    # =========================================================================
    print("─" * 80)
    print("SESSION 3: Tax-Advantaged Strategy (1 month later)")
    print("─" * 80)
    print()
    
    memory_provider = CosmosMemoryProvider(
        service_url=memory_service_url,
        user_id=user_id,  # Same user
        auto_manage_session=True  # Session starts automatically on first agent.run()
    )
    
    # Note: Session will start automatically on first agent.run()
    # You still must call end_session() explicitly when done
    
    agent = ChatAgent(
        chat_client=AzureOpenAIChatClient(credential=AzureCliCredential(), deployment_name=os.getenv("AZURE_OPENAI_REASONING_MODEL")),
        instructions=(
            "You are a knowledgeable financial advisor specializing in retirement planning. "
            "You provide personalized advice based on each client's unique situation, risk tolerance, "
            "and financial goals. Always remember important details about your clients for future sessions. "
            "Be professional, empathetic, and clear in your explanations."
        ),
        tools=[get_401k_contribution_limit, get_roth_ira_limit, calculate_retirement_needs],
        context_providers=[memory_provider],
    )
    
    thread = agent.get_new_thread()
    
    # Question: Tax strategy
    query = "I got a raise! I now make $85,000. How should I adjust my retirement strategy?"
    print(f"👤 Client: {query}")
    print("   [NOTE: Another new thread - testing cumulative memory]")
    result = await agent.run(query, thread=thread)
    print(f"💼 Advisor: {result.text[:250]}...")
    print()
    
    # Follow-up
    query = "What's the maximum I can contribute to my 401k this year?"
    print(f"👤 Client: {query}")
    result = await agent.run(query, thread=thread)
    print(f"💼 Advisor: {result.text[:150]}...")
    print()
    
    # Wait for all invoked() callbacks to complete
    await asyncio.sleep(0.5)
    
    # Explicitly end session - triggers summarization and reflection on server
    # Note: This is REQUIRED - cannot rely on context manager __aexit__
    session_id = memory_provider.session_id  # Capture before closing
    await memory_provider.end_session()
    await memory_provider.close()
    
    print("✅ Session 3 complete - Testing if agent:")
    print("   - Still remembers client profile from Session 1")
    print("   - Recalls previous advice from Session 2")
    print("   - Provides contextually appropriate recommendations")
    print()
    
    # Wait for background synthesis to complete
    print("⏳ Waiting for background synthesis...")
    wait_for_session_end(memory_service_url, session_id)
    print()
    
    # Display long-term insights
    display_longterm_insights(memory_service_url, user_id)
    
    # =========================================================================
    # FINAL STATUS CHECK
    # =========================================================================
    print("=" * 80)
    print("MEMORY SERVICE STATUS")
    print("=" * 80)
    print("✅ Demo completed successfully!")
    print(f"Client ID: {user_id}")
    print(f"Memory Service: {memory_service_url}")
    print()
    print("Note: Use the CosmosMemoryProvider for programmatic access to memory operations.")
    
    # TODO: Create a standalone MemoryServiceClient for direct API access
    # from client.memory_client import MemoryServiceClient
    # 
    # async with MemoryServiceClient(memory_service_url, user_id) as client:
    #     # Health check
    #     health = await client.health_check()
    #     print(f"Service Status: {health.get('status')}")
    #     
    #     # Pool stats
    #     stats = await client.get_stats()
    #     print(f"Session Pool:")
    #     print(f"  - Active sessions: {stats.get('total_sessions')}")
    #     print(f"  - Capacity: {stats.get('max_capacity')}")
    #     print(f"  - Utilization: {stats.get('utilization', 0):.1%}")
    #     
    #     # User insights
    #     insights = await client.get_insights()
    #     print(f"\nUser Insights: {len(insights)} total")
    #     for i, insight in enumerate(insights[:3], 1):
    #         print(f"  {i}. {insight.get('content', '')[:80]}...")
    #     
    #     # Session summaries
    #     summaries = await client.get_summaries(limit=3)
    #     print(f"\nSession Summaries: {len(summaries)} total")
    #     for i, summary in enumerate(summaries, 1):
    #         print(f"  Session {i}: {summary.get('turn_count')} turns")
    
    print()
    print("🎉 Demo Complete!")
    print()
    print("Key Capabilities Demonstrated:")
    print("✓ Long-term user profile retention (age, goals, risk tolerance)")
    print("✓ Session summaries (what was discussed in each meeting)")
    print("✓ Context continuity across new threads")
    print("✓ Personalized recommendations without re-asking questions")
    print("✓ Multi-tier memory: active turns → session summary → long-term insights")
    print()
    print("Remote Service Benefits:")
    print("✓ Simplified client code (no CosmosDB/OpenAI setup)")
    print("✓ Fast session restoration (~0ms for hot sessions)")
    print("✓ Shared resource pooling (efficient at scale)")
    print("✓ Language-agnostic (can use from any HTTP client)")


if __name__ == "__main__":
    asyncio.run(main())
